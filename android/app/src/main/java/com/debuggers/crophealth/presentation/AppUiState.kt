package com.debuggers.crophealth.presentation

import android.net.Uri
import com.debuggers.crophealth.content.Guidance
import com.debuggers.crophealth.content.Prompt
import com.debuggers.crophealth.domain.*
import java.io.File

enum class Screen { WELCOME, HOME, CAPTURE, PHOTO_REVIEW, PROCESSING, RESULT, GUIDANCE, CONCERN, HISTORY, HELP, SETTINGS }

data class ModelStatus(
    val ready: Boolean = false,
    val validated: Boolean = false,
    val name: String = "MobileNetV4-Conv-Small",
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
)

data class AppUiState(
    val screen: Screen = Screen.HOME,
    val language: AppLanguage = AppLanguage.ENGLISH,
    val selectedCrop: Crop = Crop.TOMATO,
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
    val openedObservation: Observation? = null,
)

sealed interface AppAction {
    data class Navigate(val screen: Screen) : AppAction
    data class SelectCrop(val crop: Crop) : AppAction
    data class SetLanguage(val language: AppLanguage) : AppAction
    data class ImportPhoto(val uri: Uri) : AppAction
    data class CameraCaptured(val file: File) : AppAction
    data class OpenObservation(val id: String) : AppAction
    data class DeleteObservation(val id: String) : AppAction
    data class ReportSymptoms(val symptoms: ReportedSymptoms) : AppAction
    data class SetAutoAudio(val enabled: Boolean) : AppAction
    data object Analyze : AppAction
    data object DismissError : AppAction
    data object SaveObservation : AppAction
    data object ShareCurrent : AppAction
    data object ClearHistory : AppAction
    data object CompleteWelcome : AppAction
}
