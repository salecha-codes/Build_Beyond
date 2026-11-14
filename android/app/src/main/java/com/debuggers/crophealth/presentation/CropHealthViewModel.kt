package com.debuggers.crophealth.presentation

import android.app.Application
import android.content.ClipData
import android.content.Intent
import android.net.Uri
import androidx.core.content.FileProvider
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.debuggers.crophealth.content.ContentCatalog
import com.debuggers.crophealth.content.Prompt
import com.debuggers.crophealth.data.*
import com.debuggers.crophealth.domain.*
import com.debuggers.crophealth.inference.*
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import java.io.File
import java.util.UUID

class CropHealthViewModel(application: Application) : AndroidViewModel(application) {
    private val catalog = runCatching { ContentCatalog(application) }.getOrNull()
    private val preferences = UserPreferences(application)
    private val history = ObservationStore(application)
    private val photos = PhotoStore(application)
    private val engine = LocalModelEngine(application)
    private val mutableState = MutableStateFlow(AppUiState())
    val state: StateFlow<AppUiState> = mutableState.asStateFlow()
    private var analysisJob: Job? = null

    init {
        viewModelScope.launch {
            preferences.state.collect { preference -> mutableState.update {
                it.copy(language = preference.language, autoAudio = preference.autoAudio)
            }; refreshCopy() }
        }
        viewModelScope.launch { history.observations.collect { records -> mutableState.update { it.copy(observations = records) } } }
        viewModelScope.launch {
            val status = withContext(Dispatchers.IO) { engine.load() }
            mutableState.update { it.copy(model = status) }
        }
    }

    fun text(key: String): String = catalog?.text(key, state.value.language) ?: key
    fun prompt(key: String): Prompt = catalog?.prompt(key, state.value.language) ?: Prompt(key,
        if (state.value.language == AppLanguage.KANNADA) "ಮತ್ತೊಮ್ಮೆ ಪರಿಶೀಲಿಸಿ" else "Please check again",
        if (state.value.language == AppLanguage.KANNADA) "ಸ್ಪಷ್ಟವಾದ ಎಲೆಯ ಫೋಟೋ ತೆಗೆದುಕೊಳ್ಳಿ. ಅಗತ್ಯವಿದ್ದರೆ ಕೃಷಿ ತಜ್ಞರನ್ನು ಸಂಪರ್ಕಿಸಿ."
        else "Take a clear photo of one leaf. Ask a local crop expert when needed.", null)
    fun newCameraFile(): File = photos.newCameraFile()

    fun onAction(action: AppAction) {
        when (action) {
            is AppAction.Navigate -> {
                if (state.value.processing && action.screen != Screen.PROCESSING) {
                    analysisJob?.cancel()
                    mutableState.update { it.copy(processing = false) }
                }
                mutableState.update {
                    if (action.screen == Screen.CONCERN && it.screen != Screen.CONCERN) {
                        val symptoms = ReportedSymptoms()
                        it.copy(screen = action.screen, error = null, symptoms = symptoms,
                            concern = ConcernGuidance.summarize(symptoms))
                    } else it.copy(screen = action.screen, error = null)
                }
            }
            is AppAction.SelectCrop -> if (!state.value.processing) mutableState.update {
                it.copy(selectedCrop = action.crop, assessment = null, guidance = null, savedObservationId = null, openedObservation = null)
            }
            is AppAction.SetLanguage -> viewModelScope.launch { preferences.language(action.language) }
            is AppAction.SetAutoAudio -> viewModelScope.launch { preferences.audio(action.enabled) }
            is AppAction.CameraCaptured -> acceptPhoto(action.file)
            is AppAction.ImportPhoto -> importPhoto(action.uri)
            is AppAction.Analyze -> analyze()
            is AppAction.SaveObservation -> saveObservation()
            is AppAction.OpenObservation -> openObservation(action.id)
            is AppAction.DeleteObservation -> viewModelScope.launch(Dispatchers.IO) {
                history.delete(action.id)
                mutableState.update { current ->
                    if (current.openedObservation?.id == action.id) current.copy(openedObservation = null, screen = Screen.HISTORY, photoPath = null)
                    else current
                }
            }
            is AppAction.ClearHistory -> viewModelScope.launch(Dispatchers.IO) {
                history.clear()
                mutableState.update { it.copy(openedObservation = null, savedObservationId = null, photoPath = null, assessment = null, guidance = null) }
            }
            is AppAction.ReportSymptoms -> mutableState.update {
                it.copy(symptoms = action.symptoms, concern = ConcernGuidance.summarize(action.symptoms))
            }
            AppAction.CompleteWelcome -> viewModelScope.launch {
                preferences.welcomed(); mutableState.update { it.copy(screen = Screen.HOME) }
            }
            AppAction.DismissError -> mutableState.update { it.copy(error = null) }
            AppAction.ShareCurrent -> shareCurrent()
        }
    }

    private fun importPhoto(uri: Uri) = viewModelScope.launch {
        try {
            val file = withContext(Dispatchers.IO) { photos.importPhoto(uri) }
            acceptPhoto(file)
        } catch (failure: Exception) { showError(failure.message ?: "The photo could not be opened.") }
    }

    private fun acceptPhoto(file: File) {
        if (!file.isFile || file.length() == 0L) { showError("The photo was not saved. Please try again."); return }
        analysisJob?.cancel()
        mutableState.update { it.copy(screen = Screen.PHOTO_REVIEW, photoPath = file.absolutePath,
            assessment = null, guidance = null, prompt = null, error = null, processing = false,
            inferenceMs = 0, savedObservationId = null, openedObservation = null,
            symptoms = ReportedSymptoms(), concern = ConcernGuidance.summarize(ReportedSymptoms())) }
    }

    private fun analyze() {
        val current = state.value
        if (current.processing) return
        val path = current.photoPath ?: run { showError("Take or select a leaf photo first."); return }
        mutableState.update { it.copy(screen = Screen.PROCESSING, processing = true, error = null, openedObservation = null) }
        analysisJob = viewModelScope.launch {
            try {
                val (assessment, elapsed) = withContext(Dispatchers.Default) {
                    val prepared = ImagePreparation.decode(File(path))
                    try {
                        val quality = PhotoQuality.check(prepared.quality)
                        if (!quality.acceptable) AssessmentResult.Retake(quality) to 0L
                        else {
                            val status = engine.load()
                            if (!status.ready) AssessmentResult.ModelUnavailable(ModelFailure.NOT_READY) to 0L
                            else {
                                val prediction = engine.infer(prepared.bitmap)
                                DecisionPolicy.assess(current.selectedCrop, prediction.output, prediction.policy, quality) to prediction.inferenceMs
                            }
                        }
                    } finally { prepared.bitmap.recycle() }
                }
                ensureActive()
                mutableState.update { it.copy(screen = Screen.RESULT, processing = false, assessment = assessment,
                    inferenceMs = elapsed, model = engine.status, savedObservationId = null) }
                refreshCopy()
            } catch (cancelled: CancellationException) { throw cancelled }
            catch (failure: Exception) {
                mutableState.update { it.copy(screen = Screen.PHOTO_REVIEW, processing = false,
                    error = failure.message ?: "This photo could not be assessed. Please try again.") }
            }
        }
    }

    private fun refreshCopy() {
        mutableState.update { current ->
            val condition = when (val result = current.assessment) {
                is AssessmentResult.LikelyCondition -> result.condition
                is AssessmentResult.HealthyLooking -> result.condition
                else -> null
            }
            val saved = current.openedObservation?.takeIf { it.validated }?.conditionId
            val key = when (current.assessment) {
                is AssessmentResult.Retake -> "retake"
                is AssessmentResult.ModelUnavailable -> "model_unavailable"
                is AssessmentResult.CropMismatch -> "crop_mismatch"
                is AssessmentResult.HealthyLooking -> "healthy"
                else -> "uncertain"
            }
            current.copy(guidance = (condition?.id ?: saved)?.let { catalog?.guidance(it, current.language) },
                prompt = catalog?.prompt(key, current.language))
        }
    }

    private fun saveObservation() {
        val snapshot = state.value
        if (snapshot.savedObservationId != null || snapshot.assessment == null || snapshot.photoPath == null) return
        val result = snapshot.assessment
        val type = when (result) {
            is AssessmentResult.Retake -> "retake"
            is AssessmentResult.ModelUnavailable -> "model_unavailable"
            is AssessmentResult.CropMismatch -> "crop_mismatch"
            is AssessmentResult.Uncertain -> "uncertain"
            is AssessmentResult.LikelyCondition -> "likely_condition"
            is AssessmentResult.HealthyLooking -> "healthy_looking"
        }
        val evidence = result.evidence
        val note = when (result) {
            is AssessmentResult.Uncertain -> "Uncertain: ${result.reasons.joinToString()}. Model output is not a confirmed diagnosis."
            is AssessmentResult.Retake -> "Photo needs retaking: ${result.quality.issues.joinToString()}."
            is AssessmentResult.ModelUnavailable -> "Local model unavailable: ${result.reason}. No diagnosis produced."
            is AssessmentResult.CropMismatch -> "Selected crop and model output differ. Retake or check with an expert."
            else -> "Model assessment; confirm with a crop expert when needed."
        }
        val record = Observation(UUID.randomUUID().toString(), System.currentTimeMillis(), snapshot.selectedCrop,
            snapshot.photoPath, type, evidence?.top?.condition?.id, evidence?.top?.score,
            evidence?.modelVersion ?: snapshot.model.version, snapshot.inferenceMs,
            "$note Self-reported concern: ${snapshot.concern.level} (not a photo severity score).", evidence?.calibratedAndValidated ?: false)
        // Mark before the write to make rapid repeated taps idempotent.
        mutableState.update { it.copy(savedObservationId = record.id) }
        viewModelScope.launch(Dispatchers.IO) {
            try { history.save(record) }
            catch (failure: Exception) { mutableState.update { it.copy(savedObservationId = null, error = "The observation could not be saved.") } }
        }
    }

    private fun openObservation(id: String) = viewModelScope.launch {
        val record = withContext(Dispatchers.IO) { history.find(id) } ?: return@launch
        mutableState.update { it.copy(screen = Screen.RESULT, openedObservation = record, selectedCrop = record.crop,
            photoPath = record.imagePath, assessment = null, guidance = null, savedObservationId = record.id,
            inferenceMs = record.inferenceMs, error = null) }
        refreshCopy()
    }

    private fun shareCurrent() {
        val value = state.value
        val stored = value.openedObservation
        val condition = stored?.conditionId?.let(Conditions::byId) ?: value.assessment?.evidence?.top?.condition
        val name = condition?.displayName(value.language) ?: "Uncertain observation"
        val validated = stored?.validated ?: value.assessment?.evidence?.calibratedAndValidated ?: false
        val shareText = buildString {
            appendLine("Crop Health — observation")
            appendLine("Crop: ${value.selectedCrop.nameEn}")
            appendLine("Model candidate: $name")
            appendLine(if (validated) "Model assessment; expert confirmation may be needed." else "Prototype / uncertain output. This is not a confirmed diagnosis or treatment recommendation.")
            appendLine("Model: ${stored?.modelVersion ?: value.model.version}")
            appendLine(stored?.note ?: "Please review the original leaf photo and observed symptoms.")
        }
        try {
            val intent = Intent(Intent.ACTION_SEND).apply {
                type = "text/plain"; putExtra(Intent.EXTRA_TEXT, shareText)
                val photo = value.photoPath?.let(::File)?.takeIf { it.exists() }
                if (photo != null) {
                    val uri = FileProvider.getUriForFile(getApplication<Application>(), "${getApplication<Application>().packageName}.files", photo)
                    type = "image/*"; putExtra(Intent.EXTRA_STREAM, uri)
                    clipData = ClipData.newUri(getApplication<Application>().contentResolver, "Leaf observation", uri)
                    addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                }
            }
            getApplication<Application>().startActivity(Intent.createChooser(intent, "Share observation").addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        } catch (failure: Exception) { showError("This observation could not be shared.") }
    }

    private fun showError(message: String) { mutableState.update { it.copy(error = message) } }
    override fun onCleared() { analysisJob?.cancel(); engine.close(); history.close(); super.onCleared() }
}
