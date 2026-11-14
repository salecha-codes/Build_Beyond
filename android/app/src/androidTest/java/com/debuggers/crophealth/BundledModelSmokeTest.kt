package com.debuggers.crophealth

import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import ai.onnxruntime.TensorInfo
import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.debuggers.crophealth.domain.Conditions
import com.debuggers.crophealth.inference.ImagePreparation
import com.debuggers.crophealth.inference.InputSpec
import com.debuggers.crophealth.inference.LocalModelEngine
import java.io.File
import java.nio.FloatBuffer
import java.security.MessageDigest
import kotlin.math.abs
import kotlin.math.sqrt
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

/** Executes the shipped graph on two photographic inputs; this is not an accuracy benchmark. */
@RunWith(AndroidJUnit4::class)
class BundledModelSmokeTest {
    @Test fun exactBundledV4HasBoundEvidenceAndInputDependentSeventeenScoresAnd960Features() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val app = instrumentation.targetContext
        val metadata = BundledModelContract.json(app, "model_metadata.json")
        val policy = BundledModelContract.json(app, "decision_policy.json")
        val expectedHash = metadata.getString("model_sha256")
        assertFalse("Source testing does not establish field diagnosis validation", metadata.optBoolean("diagnosis_validated", false))
        assertFalse(policy.optBoolean("validated", false))
        assertFalse(policy.optBoolean("diagnosis_validated", false))
        assertFalse(policy.optBoolean("allow_condition_specific_advice", false))
        assertEquals(17, metadata.getInt("class_count"))
        assertEquals(960, metadata.getInt("embedding_dimension"))
        LocalModelEngine(app).use { engine ->
            val status = engine.load()
            assertTrue("Shipped model and evidence must load: ${status.message}", status.ready)
            assertFalse(status.validated)
            assertFalse(status.allowConditionSpecificAdvice)
            assertEquals(BundledModelContract.sourceQualificationEnabled(metadata, policy), status.sourceEvaluated)
            if (status.sourceEvaluated) BundledModelContract.assertSourceEvidenceBinding(app, metadata, policy)
        }
        val file = File(app.filesDir, "model/$expectedHash.onnx")
        assertTrue("Engine must prepare the exact bundled model", file.isFile)
        assertEquals(expectedHash, BundledModelContract.sha256(file.readBytes()))
        val firstBytes = instrumentation.context.assets.open("leaf_input.jpg").use { it.readBytes() }
        val secondBytes = instrumentation.context.assets.open("field_leaf_input.jpg").use { it.readBytes() }
        assertEquals("eb5f9c10404aabeab5d2205a06689c4f0c966b1c7dbca20bb96c8927ccd1dae8", BundledModelContract.sha256(firstBytes))
        assertEquals("04ff0d731573d592c97f73cd2219800dcc9b4e7337c8ed90de2ec2374013a9fa", BundledModelContract.sha256(secondBytes))
        assertNotEquals("Inputs must be different original photos", BundledModelContract.sha256(firstBytes), BundledModelContract.sha256(secondBytes))
        val first = requireNotNull(BitmapFactory.decodeByteArray(firstBytes, 0, firstBytes.size))
        val second = requireNotNull(BitmapFactory.decodeByteArray(secondBytes, 0, secondBytes.size))
        try {
            val input = metadata.getJSONObject("input")
            val spec = InputSpec(input.getString("name"), input.getInt("width"), input.getInt("height"),
                FloatArray(3) { input.getJSONArray("mean").getDouble(it).toFloat() },
                FloatArray(3) { input.getJSONArray("std").getDouble(it).toFloat() },
                IntArray(3) { input.getJSONArray("padding_rgb").getInt(it) }, input.getDouble("pixel_scale").toFloat())
            val outputs = metadata.getJSONObject("outputs")
            val logitsName = outputs.getJSONObject("logits").getString("name")
            val featureName = outputs.getJSONObject("embeddings").getString("name")
            val environment = OrtEnvironment.getEnvironment()
            OrtSession.SessionOptions().use { options ->
                options.setIntraOpNumThreads(2)
                options.setInterOpNumThreads(1)
                environment.createSession(file.path, options).use { session ->
                    assertArrayEquals(longArrayOf(1, 3, 224, 224), (session.inputInfo.getValue(spec.name).info as TensorInfo).shape)
                    assertArrayEquals(longArrayOf(1, 17), (session.outputInfo.getValue(logitsName).info as TensorInfo).shape)
                    assertArrayEquals(longArrayOf(1, 960), (session.outputInfo.getValue(featureName).info as TensorInfo).shape)
                    fun infer(bitmap: Bitmap): Pair<FloatArray, FloatArray> {
                        val values = ImagePreparation.tensor(bitmap, spec)
                        assertEquals(3 * 224 * 224, values.size)
                        OnnxTensor.createTensor(environment, FloatBuffer.wrap(values), longArrayOf(1, 3, 224, 224)).use { tensor ->
                            session.run(mapOf(spec.name to tensor)).use { result ->
                                @Suppress("UNCHECKED_CAST")
                                val logits = (result.get(logitsName).get().value as Array<FloatArray>).single().copyOf()
                                @Suppress("UNCHECKED_CAST")
                                val features = (result.get(featureName).get().value as Array<FloatArray>).single().copyOf()
                                assertEquals(17, logits.size)
                                assertEquals(960, features.size)
                                assertTrue(logits.all { it.isFinite() })
                                assertTrue(features.all { it.isFinite() })
                                assertTrue("Backbone features must contain signal", features.any { abs(it) > 1e-8f })
                                return logits to features
                            }
                        }
                    }
                    val a = infer(first)
                    val b = infer(second)
                    val scoreDifference = a.first.indices.maxOf { abs(a.first[it] - b.first[it]) }
                    val featureDifference = a.second.indices.maxOf { abs(a.second[it] - b.second[it]) }
                    assertTrue("Real photos must not receive constant logits ($scoreDifference)", scoreDifference > 1e-5f)
                    assertTrue("Real photos must not receive constant features ($featureDifference)", featureDifference > 1e-5f)
                    val diagnostic = JSONObject().put("model_sha256", expectedHash)
                        .put("source_qualified", BundledModelContract.sourceQualificationEnabled(metadata, policy))
                        .put("diagnosis_validated", false).put("input_fixture_sha256", JSONArray(listOf(BundledModelContract.sha256(firstBytes), BundledModelContract.sha256(secondBytes))))
                        .put("logits_shape", JSONArray(listOf(1, 17))).put("features_shape", JSONArray(listOf(1, 960)))
                        .put("max_logit_difference", scoreDifference.toDouble()).put("max_feature_difference", featureDifference.toDouble())
                        .put("accuracy_measured", false)
                    File(app.filesDir, "review2-bundled-model-smoke.json").writeText(diagnostic.toString(2))
                    println("REVIEW2_BUNDLED_MODEL_SMOKE=$diagnostic")
                }
            }
        } finally { first.recycle(); second.recycle() }
    }
}

/** Independent assertions bind source qualification to the shipped model and frozen evidence. */
internal object BundledModelContract {
    fun json(context: Context, filename: String): JSONObject =
        context.assets.open("model/$filename").bufferedReader().use { JSONObject(it.readText()) }

    fun sha256(bytes: ByteArray): String = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }

    fun sourceQualificationEnabled(metadata: JSONObject, policy: JSONObject): Boolean =
        listOf("source_evaluated", "source_thresholds_calibrated", "source_acceptance_qualified", "source_acceptance_enabled")
            .all { metadata.optBoolean(it, false) && policy.optBoolean(it, false) }

    fun assertSourceEvidenceBinding(context: Context, metadata: JSONObject, policy: JSONObject) {
        val modelHash = metadata.getString("model_sha256")
        val version = metadata.getString("model_version")
        assertEquals(modelHash, policy.getString("model_sha256"))
        assertEquals(version, policy.getString("model_version"))
        fun checked(fileKey: String, hashKey: String, filename: String): JSONObject {
            assertEquals(filename, policy.getString(fileKey))
            val bytes = context.assets.open("model/$filename").use { it.readBytes() }
            assertEquals("Sidecar hash mismatch: $filename", policy.getString(hashKey), sha256(bytes))
            return JSONObject(bytes.toString(Charsets.UTF_8))
        }
        val report = checked("source_evaluation_file", "source_evaluation_sha256", "source_evaluation.json")
        assertEquals("source_evaluation.json", metadata.getString("source_evaluation_file"))
        assertEquals(metadata.getString("source_evaluation_sha256"), policy.getString("source_evaluation_sha256"))
        assertEquals(1, report.getInt("schema_version"))
        assertEquals(modelHash, report.getString("model_sha256"))
        assertEquals(version, report.getString("model_version"))
        assertEquals("source_domain_only", report.getString("scope"))
        assertTrue(report.getBoolean("source_acceptance_qualified"))
        assertFalse(report.getBoolean("diagnosis_validated"))
        assertFalse(report.getBoolean("field_trial_executed"))
        assertFalse(report.getBoolean("unknown_detection_validated"))
        val frozen = report.getJSONObject("frozen_policy")
        assertEquals(frozen.getDouble("temperature"), policy.getDouble("temperature"), 1e-10)
        val thresholds = policy.getJSONObject("class_thresholds")
        val recorded = frozen.getJSONObject("class_thresholds")
        assertEquals(Conditions.ids, thresholds.keys().asSequence().toSet())
        assertEquals(Conditions.ids, recorded.keys().asSequence().toSet())
        for (id in Conditions.ids) {
            val row = thresholds.getJSONObject(id)
            val reference = recorded.getJSONObject(id)
            assertEquals("Enabled class differs from frozen evidence: $id", reference.getBoolean("enabled"), row.getBoolean("enabled"))
            for (key in listOf("minimum_confidence", "minimum_margin", "max_embedding_distance")) {
                assertEquals("Frozen threshold nullability mismatch: $id/$key", reference.isNull(key), row.isNull(key))
                if (!row.isNull(key)) assertEquals("Frozen threshold changed: $id/$key", reference.getDouble(key), row.getDouble(key), 1e-10)
            }
        }
        val centroids = checked("embedding_centroids_file", "embedding_centroids_sha256", "embedding_centroids.json")
        assertEquals(policy.getString("embedding_centroids_sha256"), report.getString("embedding_centroids_sha256"))
        assertEquals(1, centroids.getInt("schema_version"))
        assertEquals(modelHash, centroids.getString("model_sha256"))
        assertEquals(version, centroids.getString("model_version"))
        assertEquals(960, centroids.getInt("embedding_dimension"))
        assertEquals("l2_per_embedding_mean_then_l2_centroid", centroids.getString("normalization"))
        assertEquals("l2_unit_embedding_to_predicted_class_centroid", centroids.getString("distance"))
        val ids = centroids.getJSONArray("label_ids")
        assertEquals(Conditions.all.map { it.id }, (0 until ids.length()).map { ids.getString(it) })
        val values = centroids.getJSONArray("centroids")
        assertEquals(17, values.length())
        for (i in 0 until values.length()) {
            val vector = values.getJSONArray(i)
            assertEquals(960, vector.length())
            val squaredNorm = (0 until vector.length()).sumOf { j -> vector.getDouble(j).also { assertTrue(it.isFinite()) }.let { it * it } }
            assertEquals("Centroid must be normalized for native distances", 1.0, sqrt(squaredNorm), 1e-3)
        }
    }
}
