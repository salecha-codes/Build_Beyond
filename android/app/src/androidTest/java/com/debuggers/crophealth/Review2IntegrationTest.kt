package com.debuggers.crophealth

import android.Manifest
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Color
import androidx.exifinterface.media.ExifInterface
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.debuggers.crophealth.data.ObservationStore
import com.debuggers.crophealth.domain.*
import com.debuggers.crophealth.inference.ImagePreparation
import com.debuggers.crophealth.inference.LocalModelEngine
import com.debuggers.crophealth.inference.InputSpec
import com.debuggers.crophealth.presentation.Observation
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.UUID
import kotlin.math.abs
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

/** Native Android checks. Test inputs do not seed or fabricate production scan results. */
@RunWith(AndroidJUnit4::class)
class Review2IntegrationTest {
    private val instrumentation get() = InstrumentationRegistry.getInstrumentation()
    private val app get() = instrumentation.targetContext

    private fun leafFixture(): File = File(app.cacheDir, "qa-leaf-${UUID.randomUUID()}.jpg").also { file ->
        instrumentation.context.assets.open("leaf_input.jpg").use { input ->
            file.outputStream().use { output -> input.copyTo(output) }
        }
    }

    @Test fun installedAppHasCameraButNoInternetPermission() {
        @Suppress("DEPRECATION")
        val installed = app.packageManager.getPackageInfo(app.packageName, PackageManager.GET_PERMISSIONS)
        val permissions = installed.requestedPermissions?.toSet().orEmpty()
        assertTrue("Camera capture must remain declared", Manifest.permission.CAMERA in permissions)
        assertFalse("Offline diagnosis must not request Internet access", Manifest.permission.INTERNET in permissions)
    }

    @Test fun bundledV4ExecutesOnAndroidAndRemainsExplicitlyUnvalidated() {
        val fixture = leafFixture()
        val photo = ImagePreparation.decode(fixture)
        try {
            assertTrue(photo.quality.meanLuminance.isFinite())
            assertTrue(photo.quality.laplacianVariance.isFinite())
            assertTrue(photo.bitmap.width <= 1024 && photo.bitmap.height <= 1024)
            val metadata = app.assets.open("model/model_metadata.json").bufferedReader().use { JSONObject(it.readText()) }
            LocalModelEngine(app).use { engine ->
                val status = engine.load()
                assertTrue("Real bundled model must load: ${status.message}", status.ready)
                assertEquals("MobileNetV4-Conv-Small", status.name)
                assertFalse("Prototype must not advertise validated diagnosis", status.validated)
                val prediction = engine.infer(photo.bitmap)
                assertEquals(Conditions.ids, prediction.output.labelIds.toSet())
                assertEquals(metadata.getInt("class_count"), prediction.output.logits.size)
                assertEquals(17, prediction.output.logits.size)
                assertTrue("Native ONNX outputs must be finite", prediction.output.logits.all { it.isFinite() })
                assertFalse(prediction.policy.validated)
                assertEquals(status.version, prediction.output.modelVersion)
                // The engine checks its actual embedding against this model-specific dimension.
                assertTrue(metadata.getInt("embedding_dimension") > 0)
                val highest = prediction.output.logits.indices.maxBy { prediction.output.logits[it] }
                val predictedCrop = Conditions.byId(prediction.output.labelIds[highest])!!.crop
                val result = DecisionPolicy.assess(predictedCrop, prediction.output, prediction.policy)
                assertTrue("Unvalidated inference must not become a confident diagnosis", result is AssessmentResult.Uncertain)
                val uncertain = result as AssessmentResult.Uncertain
                assertTrue(UncertaintyReason.MODEL_NOT_VALIDATED in uncertain.reasons)
                assertEquals(17, uncertain.evidence.ranked.size)
                assertFalse(uncertain.evidence.calibratedAndValidated)
                assertNotNull("Verified model copy must exist", File(app.filesDir, "model").listFiles()?.firstOrNull {
                    it.name == metadata.getString("model_sha256") + ".onnx"
                })
            }
        } finally {
            photo.bitmap.recycle()
            fixture.delete()
        }
    }

    @Test fun unvalidatedModelCannotAssertTheFarmerSelectedTheWrongCrop() {
        val logits = Conditions.all.map { if (it.id == "potato_early_blight") 20f else -20f }
        val result = DecisionPolicy.assess(
            Crop.TOMATO,
            InferenceOutput(Conditions.all.map { it.id }, logits, "qa-unvalidated"),
            PolicyConfig(validated = false),
        )
        assertTrue("Unvalidated crop scores must remain uncertain, not a crop correction", result is AssessmentResult.Uncertain)
        assertTrue(UncertaintyReason.MODEL_NOT_VALIDATED in (result as AssessmentResult.Uncertain).reasons)
        assertEquals("potato_early_blight", result.evidence.top.condition.id)
    }

    @Test fun decodeBoundsLargePhotosAndAppliesExifOrientation() {
        val file = File(app.cacheDir, "qa-orientation-${UUID.randomUUID()}.jpg")
        val original = Bitmap.createBitmap(2048, 1024, Bitmap.Config.ARGB_8888)
        original.eraseColor(Color.rgb(40, 140, 65))
        try {
            file.outputStream().use { stream -> assertTrue(original.compress(Bitmap.CompressFormat.JPEG, 90, stream)) }
            ExifInterface(file).apply {
                setAttribute(ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_ROTATE_90.toString())
                saveAttributes()
            }
            val decoded = ImagePreparation.decode(file)
            try {
                assertEquals(512, decoded.bitmap.width)
                assertEquals(1024, decoded.bitmap.height)
                assertEquals(decoded.bitmap.width, decoded.quality.width)
                assertEquals(decoded.bitmap.height, decoded.quality.height)
            } finally { decoded.bitmap.recycle() }
        } finally {
            original.recycle()
            file.delete()
        }
    }

    @Test fun solidAndTexturedTensorsMatchPythonGolden() {
        val metadata = app.assets.open("model/model_metadata.json").bufferedReader().use { JSONObject(it.readText()) }
        val input = metadata.getJSONObject("input")
        val spec = InputSpec(input.getString("name"), input.getInt("width"), input.getInt("height"),
            FloatArray(3) { input.getJSONArray("mean").getDouble(it).toFloat() },
            FloatArray(3) { input.getJSONArray("std").getDouble(it).toFloat() },
            IntArray(3) { input.getJSONArray("padding_rgb").getInt(it) },
            input.getDouble("pixel_scale").toFloat())
        fun comparison(name: String): JSONObject {
            val bitmap = instrumentation.context.assets.open("golden/$name.png").use { BitmapFactory.decodeStream(it) }
                ?: error("Golden fixture could not be decoded: $name")
            try {
                val actual = ImagePreparation.tensor(bitmap, spec)
                val bytes = instrumentation.context.assets.open("golden/$name.f32").use { it.readBytes() }
                assertEquals(1 * 3 * 224 * 224 * 4, bytes.size)
                val expected = FloatArray(bytes.size / 4)
                ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN).asFloatBuffer().get(expected)
                assertEquals(expected.size, actual.size)
                assertTrue(actual.all { it.isFinite() })
                assertTrue(expected.all { it.isFinite() })
                val differences = FloatArray(actual.size) { abs(actual[it] - expected[it]) }
                val mean = differences.sumOf { it.toDouble() } / differences.size
                differences.sort()
                return JSONObject().put("values", differences.size)
                    .put("max_abs_error", differences.last().toDouble())
                    .put("mean_abs_error", mean)
                    .put("p99_abs_error", differences[(differences.size * .99).toInt()].toDouble())
            } finally { bitmap.recycle() }
        }
        val solid = comparison("solid_letterbox")
        assertTrue("All solid fixture values must match within 1e-5: $solid", solid.getDouble("max_abs_error") <= 1e-5)
        val textured = comparison("leaf_letterbox")
        val diagnostic = JSONObject().put("solid_letterbox", solid).put("leaf_letterbox", textured)
            .put("acceptance_absolute_tolerance", 1e-5)
            .put("textured_acceptance", "all values must match within absolute 1e-5")
        File(app.filesDir, "review2-preprocessing-diagnostics.json").writeText(diagnostic.toString(2))
        println("REVIEW2_PREPROCESSING_DIAGNOSTIC=$diagnostic")
        assertTrue("All textured fixture values must match Python within 1e-5: $textured",
            textured.getDouble("max_abs_error") <= 1e-5)
    }

    @Test fun observationPersistsAndDeletionOnlyRemovesItsOwnedImage() = runBlocking {
        val id = "qa-${UUID.randomUUID()}"
        val directory = File(app.filesDir, "observations").apply { mkdirs() }
        val owned = File(directory, "$id.jpg")
        instrumentation.context.assets.open("leaf_input.jpg").use { input -> owned.outputStream().use { input.copyTo(it) } }
        val store = ObservationStore(app)
        val reopened = ObservationStore(app)
        try {
            val observation = Observation(
                id = id, createdAt = System.currentTimeMillis(), crop = Crop.TOMATO,
                imagePath = owned.path, resultType = "UNCERTAIN", conditionId = "tomato_healthy",
                score = .2f, modelVersion = "qa-persistence-fixture", inferenceMs = 0,
                note = "Instrumentation record, not an inference result", validated = false,
            )
            store.save(observation)
            // A second repository connection must retrieve the committed disk-backed record.
            val restored = reopened.find(id)
            assertEquals(observation, restored)
            assertTrue(owned.isFile)
            store.delete(id)
            assertNull(reopened.find(id))
            assertFalse("Deleting the last owned reference must delete its photo", owned.exists())

            val outside = File(app.cacheDir, "$id-outside.jpg").apply { writeText("not an owned observation image") }
            try {
                store.save(observation.copy(id = "$id-outside", imagePath = outside.path))
                store.delete("$id-outside")
                assertTrue("Repository deletion must not remove arbitrary paths", outside.exists())
            } finally { outside.delete() }
        } finally {
            store.delete(id)
            store.delete("$id-outside")
            owned.delete()
            reopened.close()
            store.close()
        }
    }
}
