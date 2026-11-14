package com.debuggers.crophealth.presentation

import android.net.Uri
import com.debuggers.crophealth.content.Guidance
import com.debuggers.crophealth.content.Prompt
import com.debuggers.crophealth.content.AdvisoryProfile
import com.debuggers.crophealth.content.CareProtocol
import com.debuggers.crophealth.domain.*
import java.io.File

enum class Screen { WELCOME, HOME, CAPTURE, PHOTO_REVIEW, PROCESSING, RESULT, GUIDANCE, CONCERN, CARE_LIBRARY, HISTORY, HELP, SETTINGS }

/** Library exploration never changes the classifier result or a saved scan. */
data class ManualCareSession(val conditionId: String, val symptoms: ReportedSymptoms = ReportedSymptoms(),
    val completed: Boolean = false)

data class ModelStatus(
    val ready: Boolean = false,
    val validated: Boolean = false,
    val name: String = "Crop disease model",
    val version: String = "Not installed",
    val message: String = "Checking local model…",
    val bytes: Long = 0,
    val sourceEvaluated: Boolean = false,
    val allowConditionSpecificAdvice: Boolean = false,
)

data class Observation(
    val id: String,
    val createdAt: Long,
    val crop: Crop,
    val imagePath: String?,
    val resultType: String,
    val conditionId: String?,
    val score: Float?,
    val modelVersion: String,
    val inferenceMs: Long,
    val note: String,
    val validated: Boolean = false,
    val reportedSymptoms: ReportedSymptoms? = null,
)

/** Persisted provenance is explicit; legacy unsupported records must never gain candidate status. */
fun Observation.isLeafCheckedCandidate(): Boolean = resultType == "uncertain" &&
    note.startsWith(LEAF_CHECKED_CANDIDATE_NOTE) && conditionId?.let(Conditions::byId) != null &&
    score?.let { it.isFinite() && it in 0f..1f } == true

fun Observation.hidesUnsupportedCandidate(): Boolean =
    ("UNFAMILIAR_IMAGE" in note || "CONDITION_DISABLED" in note) && !isLeafCheckedCandidate()

data class AppUiState(
    val screen: Screen = Screen.HOME,
    val language: AppLanguage = AppLanguage.ENGLISH,
    val selectedCrop: Crop = Crop.MAIZE,
    val photoPath: String? = null,
    val assessment: AssessmentResult? = null,
    val guidance: Guidance? = null,
    val prompt: Prompt? = null,
    val model: ModelStatus = ModelStatus(),
    val observations: List<Observation> = emptyList(),
    val processing: Boolean = false,
    val error: String? = null,
    val inferenceMs: Long = 0,
    val savedObservationId: String? = null,
    val autoAudio: Boolean = false,
    val symptoms: ReportedSymptoms = ReportedSymptoms(),
    val concern: ConcernResult = ConcernGuidance.summarize(ReportedSymptoms()),
    val symptomsComplete: Boolean = false,
    val advisoryProfile: AdvisoryProfile? = null,
    val advisory: AdvisoryAssessment = AdvisoryDecisionModel.assess(null, null, null),
    val careProtocol: CareProtocol? = null,
    val manualCare: ManualCareSession? = null,
    val careLibraryReturn: Screen = Screen.HOME,
    val careCatalogAvailable: Boolean = false,
    val openedObservation: Observation? = null,
)

val AppUiState.careSymptoms: ReportedSymptoms get() = manualCare?.symptoms ?: symptoms
val AppUiState.careSymptomsComplete: Boolean get() = manualCare?.completed ?: symptomsComplete
fun AppUiState.backScreen(): Screen = when (screen) {
    Screen.GUIDANCE -> if (manualCare != null) Screen.CARE_LIBRARY else Screen.RESULT
    Screen.CONCERN -> if (manualCare != null) {
        if (careSymptomsComplete) Screen.GUIDANCE else Screen.CARE_LIBRARY
    } else Screen.RESULT
    Screen.CARE_LIBRARY -> careLibraryReturn
    Screen.SETTINGS -> Screen.HELP
    Screen.RESULT -> if (openedObservation != null) Screen.HISTORY else Screen.HOME
    else -> Screen.HOME
}

fun AppUiState.selectManualCare(conditionId: String): AppUiState =
    if (Conditions.byId(conditionId) == null) this else copy(screen = Screen.CONCERN,
        manualCare = ManualCareSession(conditionId), error = null)

fun AppUiState.reportCareSymptoms(value: ReportedSymptoms, completed: Boolean): AppUiState =
    if (manualCare != null) copy(manualCare = manualCare.copy(symptoms = value, completed = completed))
    else copy(symptoms = value, concern = ConcernGuidance.summarize(value), symptomsComplete = completed)

sealed interface AppAction {
    data class Navigate(val screen: Screen) : AppAction
    data class SelectCrop(val crop: Crop) : AppAction
    data class SetLanguage(val language: AppLanguage) : AppAction
    data class ImportPhoto(val uri: Uri) : AppAction
    data class CameraCaptured(val file: File) : AppAction
    data class OpenObservation(val id: String) : AppAction
    data class DeleteObservation(val id: String) : AppAction
    data class ReportSymptoms(val symptoms: ReportedSymptoms, val completed: Boolean = false) : AppAction
    data class SelectCareCondition(val conditionId: String) : AppAction
    data object OpenCareLibrary : AppAction
    data object ReloadCareProtocols : AppAction
    data class SetAutoAudio(val enabled: Boolean) : AppAction
    data object Analyze : AppAction
    data object DismissError : AppAction
    data object SaveObservation : AppAction
    data object ShareCurrent : AppAction
    data object ClearHistory : AppAction
    data object CompleteWelcome : AppAction
}
