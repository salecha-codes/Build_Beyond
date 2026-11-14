package com.debuggers.crophealth.ui

import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.debuggers.crophealth.content.Prompt
import com.debuggers.crophealth.domain.*
import com.debuggers.crophealth.presentation.*
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.util.concurrent.CopyOnWriteArrayList

/** Static states are test fixtures only; production UI receives real VM state. */
@RunWith(AndroidJUnit4::class)
class UiSmokeTest {
    @get:Rule val compose = createComposeRule()
    private fun show(state:AppUiState,actions:MutableList<AppAction>) {
        compose.setContent {
            CropHealthScreen(state,actions::add,{it},{Prompt(it,"Test prompt","Test observation guidance",null)},{File("unused-camera-fixture.jpg")})
        }
    }

    @Test fun homeScanDispatchesCaptureAndLanguageCanChange() {
        val actions=CopyOnWriteArrayList<AppAction>()
        show(AppUiState(screen=Screen.HOME),actions)
        compose.onNodeWithText("Check your crop").assertIsDisplayed()
        compose.onNodeWithTag("language_kn").performClick()
        compose.runOnIdle {assertTrue(actions.contains(AppAction.SetLanguage(AppLanguage.KANNADA)))}
        compose.onNodeWithTag("home_scan").performClick()
        compose.runOnIdle {assertTrue(actions.contains(AppAction.Navigate(Screen.CAPTURE)))}
    }

    @Test fun unvalidatedScoresRemainExplicitlyUncertain() {
        val evidence=PredictionEvidence(listOf(RankedPrediction(Conditions.all[0],.7f),RankedPrediction(Conditions.all[1],.2f)),"test-fixture",false,null)
        val result=AssessmentResult.Uncertain(setOf(UncertaintyReason.MODEL_NOT_VALIDATED),evidence)
        show(AppUiState(screen=Screen.RESULT,selectedCrop=Crop.MAIZE,assessment=result),CopyOnWriteArrayList())
        compose.onNodeWithText("Not sure about this one").assertIsDisplayed()
        compose.onNodeWithText("Model score · unvalidated").assertExists()
        compose.onNodeWithText("Model confidence").assertDoesNotExist()
        compose.onNodeWithText("Possible — not confirmed").assertExists()
    }

    @Test fun symptomQuestionRequiresAnExplicitAnswer() {
        show(AppUiState(screen=Screen.CONCERN),CopyOnWriteArrayList())
        compose.onNodeWithText("Next").performScrollTo().assertIsNotEnabled()
        compose.onNodeWithText("Yes").performScrollTo().performClick()
        compose.onNodeWithText("Next").performScrollTo().assertIsEnabled()
    }

    @Test fun historyEmptyStateAndHelpNavigationAreAvailableOffline() {
        val actions=CopyOnWriteArrayList<AppAction>()
        show(AppUiState(screen=Screen.HISTORY),actions)
        compose.onNodeWithText("No scans here yet").assertExists()
        compose.onNodeWithText("Help").performClick()
        compose.runOnIdle {assertTrue(actions.contains(AppAction.Navigate(Screen.HELP)))}
    }
}
