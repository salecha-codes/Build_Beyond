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
import kotlin.math.abs
import kotlin.math.sqrt

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
    private var centroids: Map<String, FloatArray> = emptyMap()
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
            require(metadata.getString("architecture") in setOf("MobileNetV4-Conv-Small", "MobileNetV3-Large"))
            require(metadata.getInt("class_count") == labelIds.size)
            val input = metadata.getJSONObject("input")
            require(input.getString("layout") == "NCHW" && input.getString("color_order") == "RGB")
            require(input.getString("dtype") == "float32" && input.getString("resize") == "letterbox")
            require(input.getString("resize_rounding") == "half_up" && input.getString("interpolation") == "bilinear")
            spec = InputSpec(input.getString("name"), input.getInt("width"), input.getInt("height"),
                FloatArray(3) { input.getJSONArray("mean").getDouble(it).toFloat() },
                FloatArray(3) { input.getJSONArray("std").getDouble(it).toFloat() },
                IntArray(3) { input.getJSONArray("padding_rgb").getInt(it) }, input.getDouble("pixel_scale").toFloat())
            require(spec.width == 224 && spec.height == 224 && spec.std.all { it > 0 && it.isFinite() })
            require(spec.mean.all { it.isFinite() } && spec.pixelScale.isFinite() && spec.pixelScale > 0)
            embeddingDimension = metadata.getInt("embedding_dimension")
            require(embeddingDimension == 960)
            val outputs = metadata.getJSONObject("outputs")
            outputName = outputs.getJSONObject("logits").getString("name")
            embeddingName = outputs.getJSONObject("embeddings").getString("name")
            val version = metadata.getString("model_version")
            require(artifactPolicy.getString("model_version") == version)
            val expected = metadata.getString("model_sha256").lowercase()
            require(expected.matches(Regex("[0-9a-f]{64}")))
            require(!artifactPolicy.has("model_sha256") || artifactPolicy.getString("model_sha256") == expected)
            val validated = metadata.optBoolean("diagnosis_validated", false) &&
                artifactPolicy.optBoolean("validated", false) && artifactPolicy.optBoolean("thresholds_calibrated", false)
            val sourceEvaluated = loadSourceQualification(metadata, artifactPolicy, expected, version)
            val thresholds = if (sourceEvaluated) artifactPolicy.getJSONObject("class_thresholds").let { table ->
                require(table.keys().asSequence().toSet() == Conditions.ids)
                labelIds.associateWith { id -> table.getJSONObject(id).let { row ->
                    ClassAcceptanceThreshold(row.getBoolean("enabled"),
                        row.takeUnless { it.isNull("minimum_confidence") }?.getDouble("minimum_confidence")?.toFloat(),
                        row.takeUnless { it.isNull("minimum_margin") }?.getDouble("minimum_margin")?.toFloat(),
                        row.takeIf { it.has("max_embedding_distance") && !it.isNull("max_embedding_distance") }
                            ?.getDouble("max_embedding_distance")?.toFloat())
                } }
            } else emptyMap()
            policy = PolicyConfig(validated = validated,
                temperature = artifactPolicy.optDouble("temperature", 1.0).toFloat(),
                minConfidence = artifactPolicy.optDouble("min_confidence", .8).toFloat(),
                minMargin = artifactPolicy.optDouble("min_margin", .15).toFloat(),
                maxEmbeddingDistance = artifactPolicy.takeIf { it.has("max_embedding_distance") && !it.isNull("max_embedding_distance") }
                    ?.getDouble("max_embedding_distance")?.toFloat(),
                enabledConditionIds = artifactPolicy.optJSONArray("enabled_condition_ids")?.let { ids ->
                    (0 until ids.length()).map { ids.getString(it) }.toSet()
                } ?: Conditions.ids,
                sourceEvaluated = sourceEvaluated, classThresholds = thresholds,
                allowConditionSpecificAdvice = validated && artifactPolicy.optBoolean("allow_condition_specific_advice", false))
            val fileName = metadata.getString("model_file")
            require(fileName == "crop_model.onnx")
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
                    sourceEvaluated -> "Dataset-tested prototype model"
                    training.startsWith("untrained") -> "Integration model only — not trained for diagnosis"
                    else -> "Prototype model — not validated for diagnosis"
                }, modelFile.length(), sourceEvaluated, policy.allowConditionSpecificAdvice)
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
        lateinit var features: FloatArray
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
                    features = embeddings[0].copyOf()
                }
            }
        }
        val top = logits.indices.maxBy { logits[it] }
        val distance = centroids[labelIds[top]]?.let { centroid ->
            val norm = sqrt(features.sumOf { it.toDouble() * it })
            require(norm.isFinite() && norm > 1e-12) { "Model features are empty" }
            sqrt(features.indices.sumOf { i ->
                val difference = features[i] / norm - centroid[i]
                difference * difference
            }).toFloat()
        }
        return EnginePrediction(InferenceOutput(labelIds, logits.toList(), status.version, true, distance), policy, nanos / 1_000_000)
    }

    /** A source-tested estimate is enabled only by evidence for this exact exported file. */
    private fun loadSourceQualification(metadata: JSONObject, candidate: JSONObject, expected: String, version: String): Boolean {
        centroids = emptyMap()
        val qualified = metadata.optBoolean("source_evaluated", false) &&
            metadata.optBoolean("source_thresholds_calibrated", false) &&
            metadata.optBoolean("source_acceptance_qualified", false) && metadata.optBoolean("source_acceptance_enabled", false) &&
            candidate.optBoolean("source_evaluated", false) && candidate.optBoolean("source_thresholds_calibrated", false) &&
            candidate.optBoolean("source_acceptance_qualified", false) && candidate.optBoolean("source_acceptance_enabled", false)
        if (!qualified) return false
        val report = checkedAssetJson(candidate, "source_evaluation_file", "source_evaluation_sha256", "source_evaluation.json")
        require(report.getInt("schema_version") == 1 && report.getString("model_version") == version &&
            report.getString("model_sha256") == expected && report.getString("scope") == "source_domain_only" &&
            report.getBoolean("source_acceptance_qualified")) { "Source evaluation does not qualify this model" }
        val frozen = report.getJSONObject("frozen_policy")
        require(abs(frozen.getDouble("temperature") - candidate.getDouble("temperature")) < 1e-10)
        val table = candidate.getJSONObject("class_thresholds")
        val recorded = frozen.getJSONObject("class_thresholds")
        require(table.keys().asSequence().toSet() == Conditions.ids && recorded.keys().asSequence().toSet() == Conditions.ids)
        for (id in labelIds) {
            val row = table.getJSONObject(id)
            val reference = recorded.getJSONObject(id)
            require(row.getBoolean("enabled") == reference.getBoolean("enabled"))
            for (key in listOf("minimum_confidence", "minimum_margin")) {
                require(row.has(key) && reference.has(key))
                val missing = row.isNull(key)
                require(missing == reference.isNull(key))
                if (missing) {
                    require(!row.getBoolean("enabled")) { "Enabled source class lacks acceptance thresholds" }
                    continue
                }
                val value = row.getDouble(key)
                require(value.isFinite() && value in 0.0..1.0 && abs(value - reference.getDouble(key)) < 1e-10)
                if (row.getBoolean("enabled")) require(value > 0.0)
            }
            val missingDistance = !row.has("max_embedding_distance") || row.isNull("max_embedding_distance")
            val recordedMissing = !reference.has("max_embedding_distance") || reference.isNull("max_embedding_distance")
            require(missingDistance == recordedMissing)
            if (!missingDistance) {
                val distance = row.getDouble("max_embedding_distance")
                require(distance.isFinite() && distance in 0.0..2.00001 &&
                    abs(distance - reference.getDouble("max_embedding_distance")) < 1e-10)
            }
            if (row.getBoolean("enabled")) require(!missingDistance) { "Enabled source class lacks a feature-distance bound" }
        }
        val basis = checkedAssetJson(candidate, "embedding_centroids_file", "embedding_centroids_sha256", "embedding_centroids.json")
        require(basis.getInt("schema_version") == 1 && basis.getString("model_version") == version &&
            basis.getString("model_sha256") == expected && basis.getInt("embedding_dimension") == embeddingDimension &&
            basis.getString("normalization") == "l2_per_embedding_mean_then_l2_centroid" &&
            basis.getString("distance") == "l2_unit_embedding_to_predicted_class_centroid")
        val ids = basis.getJSONArray("label_ids")
        require((0 until ids.length()).map { ids.getString(it) } == labelIds)
        val values = basis.getJSONArray("centroids")
        require(values.length() == labelIds.size)
        centroids = labelIds.indices.associate { index ->
            val row = values.getJSONArray(index)
            require(row.length() == embeddingDimension)
            val vector = FloatArray(embeddingDimension) { row.getDouble(it).toFloat() }
            require(vector.all { it.isFinite() } && abs(sqrt(vector.sumOf { it.toDouble() * it }) - 1.0) < 1e-3)
            labelIds[index] to vector
        }
        return true
    }

    private fun checkedAssetJson(policy: JSONObject, fileKey: String, hashKey: String, fileName: String): JSONObject {
        require(policy.getString(fileKey) == fileName)
        val expected = policy.getString(hashKey).lowercase()
        require(expected.matches(Regex("[0-9a-f]{64}")))
        val bytes = context.assets.open("model/$fileName").use { it.readBytes() }
        val actual = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
        require(actual == expected) { "Source-evaluation asset integrity check failed" }
        return JSONObject(bytes.toString(Charsets.UTF_8))
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
