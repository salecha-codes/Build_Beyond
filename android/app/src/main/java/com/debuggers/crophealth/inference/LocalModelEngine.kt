package com.debuggers.crophealth.inference

import android.content.Context
import android.graphics.Bitmap
import ai.onnxruntime.*
import com.debuggers.crophealth.domain.*
import com.debuggers.crophealth.presentation.ModelStatus
import org.json.JSONObject
import java.io.File
import java.nio.FloatBuffer
import java.security.MessageDigest
import kotlin.system.measureNanoTime

data class EnginePrediction(val output: InferenceOutput, val policy: PolicyConfig, val inferenceMs: Long)

/** Executes only an integrity-checked, locally bundled model. There is no network client or fake fallback. */
class LocalModelEngine(private val context: Context) : AutoCloseable {
    private val environment by lazy { OrtEnvironment.getEnvironment() }
    private var session: OrtSession? = null
    private lateinit var spec: InputSpec
    private var labelIds: List<String> = emptyList()
    private var outputName = "logits"
    private var embeddingName = "embeddings"
    private var embeddingDimension = 0
    private var policy = PolicyConfig()
    var status: ModelStatus = ModelStatus()
        private set

    @Synchronized fun load(): ModelStatus {
        if (session != null) return status
        return try {
            val metadata = assetJson("model/model_metadata.json")
            val labelsRoot = assetJson("model/labels.json")
            val artifactPolicy = assetJson("model/decision_policy.json")
            val labels = labelsRoot.getJSONArray("labels")
            labelIds = (0 until labels.length()).map { index ->
                val label = labels.getJSONObject(index)
                require(label.getInt("index") == index) { "Model class order mismatch" }
                val id = label.getString("id")
                require(Conditions.byId(id)?.sourceLabel == label.getString("source_label")) { "Model labels are incompatible" }
                id
            }
            require(labelIds.size == 17 && labelIds.toSet() == Conditions.ids)
            require(metadata.getInt("class_count") == labelIds.size)
            val input = metadata.getJSONObject("input")
            require(input.getString("layout") == "NCHW" && input.getString("color_order") == "RGB")
            require(input.getString("dtype") == "float32" && input.getString("resize") == "letterbox")
            spec = InputSpec(input.getString("name"), input.getInt("width"), input.getInt("height"),
                FloatArray(3) { input.getJSONArray("mean").getDouble(it).toFloat() },
                FloatArray(3) { input.getJSONArray("std").getDouble(it).toFloat() },
                IntArray(3) { input.getJSONArray("padding_rgb").getInt(it) }, input.getDouble("pixel_scale").toFloat())
            require(spec.width == 224 && spec.height == 224 && spec.std.all { it > 0 && it.isFinite() })
            require(spec.mean.all { it.isFinite() } && spec.pixelScale.isFinite() && spec.pixelScale > 0)
            embeddingDimension = metadata.getInt("embedding_dimension")
            require(embeddingDimension in 1..8192)
            val outputs = metadata.getJSONObject("outputs")
            outputName = outputs.getJSONObject("logits").getString("name")
            embeddingName = outputs.getJSONObject("embeddings").getString("name")
            val version = metadata.getString("model_version")
            require(artifactPolicy.getString("model_version") == version)
            val validated = metadata.optBoolean("diagnosis_validated", false) && artifactPolicy.optBoolean("validated", false)
            policy = PolicyConfig(validated = validated,
                temperature = artifactPolicy.optDouble("temperature", 1.0).toFloat(),
                minConfidence = artifactPolicy.optDouble("min_confidence", .8).toFloat(),
                minMargin = artifactPolicy.optDouble("min_margin", .15).toFloat(),
                maxEmbeddingDistance = artifactPolicy.takeIf { it.has("max_embedding_distance") && !it.isNull("max_embedding_distance") }
                    ?.getDouble("max_embedding_distance")?.toFloat(),
                enabledConditionIds = artifactPolicy.optJSONArray("enabled_condition_ids")?.let { ids ->
                    (0 until ids.length()).map { ids.getString(it) }.toSet()
                } ?: Conditions.ids)
            val fileName = metadata.getString("model_file")
            require(fileName == "crop_model.onnx")
            val expected = metadata.getString("model_sha256").lowercase()
            require(expected.matches(Regex("[0-9a-f]{64}")))
            val modelFile = verifiedModelFile(fileName, expected)
            val newSession = OrtSession.SessionOptions().use { options ->
                options.setIntraOpNumThreads(2)
                options.setInterOpNumThreads(1)
                options.setOptimizationLevel(OrtSession.SessionOptions.OptLevel.ALL_OPT)
                environment.createSession(modelFile.path, options)
            }
            try {
                require((newSession.inputInfo.getValue(spec.name).info as TensorInfo).shape.contentEquals(longArrayOf(1, 3, 224, 224)))
                require(newSession.outputNames.containsAll(listOf(outputName, embeddingName)))
                session = newSession
            } catch (failure: Exception) { newSession.close(); throw failure }
            val training = metadata.optString("training_status", "unknown")
            status = ModelStatus(true, validated, metadata.getString("architecture"), version,
                when {
                    validated -> "Local model installed"
                    training.startsWith("untrained") -> "Integration model only — not trained for diagnosis"
                    else -> "Prototype model — not validated for diagnosis"
                }, modelFile.length())
            status
        } catch (failure: Exception) {
            status = ModelStatus(message = "Local model unavailable: ${failure.message ?: "asset check failed"}")
            status
        }
    }

    @Synchronized fun infer(bitmap: Bitmap): EnginePrediction {
        val active = session ?: error("The local model is unavailable.")
        val data = ImagePreparation.tensor(bitmap, spec)
        lateinit var logits: FloatArray
        var nanos = 0L
        OnnxTensor.createTensor(environment, FloatBuffer.wrap(data), longArrayOf(1, 3, spec.height.toLong(), spec.width.toLong())).use { input ->
            nanos = measureNanoTime {
                active.run(mapOf(spec.name to input)).use { result ->
                    val logitsTensor = result.get(outputName).orElseThrow { IllegalStateException("Model scores missing") }
                    val embeddingTensor = result.get(embeddingName).orElseThrow { IllegalStateException("Model embedding missing") }
                    @Suppress("UNCHECKED_CAST")
                    val rows = logitsTensor.value as Array<FloatArray>
                    @Suppress("UNCHECKED_CAST")
                    val embeddings = embeddingTensor.value as Array<FloatArray>
                    require(rows.size == 1 && rows[0].size == labelIds.size)
                    require(embeddings.size == 1 && embeddings[0].size == embeddingDimension)
                    require(rows[0].all { it.isFinite() } && embeddings[0].all { it.isFinite() })
                    logits = rows[0].copyOf()
                }
            }
        }
        // A centroid-distance gate is not claimed until the artifact provides validated centroid data.
        return EnginePrediction(InferenceOutput(labelIds, logits.toList(), status.version, true, null), policy, nanos / 1_000_000)
    }

    private fun assetJson(path: String): JSONObject = context.assets.open(path).bufferedReader().use { JSONObject(it.readText()) }

    private fun verifiedModelFile(name: String, expected: String): File {
        val directory = File(context.filesDir, "model").apply { mkdirs() }
        val target = File(directory, "$expected.onnx")
        if (target.exists() && hash(target) == expected) return target
        target.delete()
        val temporary = File.createTempFile("$expected-", ".tmp", directory)
        try {
            context.assets.open("model/$name").use { input -> temporary.outputStream().use { input.copyTo(it) } }
            require(hash(temporary) == expected) { "Model integrity check failed" }
            require(temporary.renameTo(target) || (target.isFile && hash(target) == expected)) { "Model could not be prepared" }
            directory.listFiles()?.filter { it != target && it.extension == "onnx" }?.forEach { it.delete() }
            return target
        } finally { temporary.delete() }
    }

    private fun hash(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { stream ->
            val buffer = ByteArray(8192)
            while (true) { val count = stream.read(buffer); if (count < 0) break; digest.update(buffer, 0, count) }
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }

    @Synchronized override fun close() { session?.close(); session = null }
}
