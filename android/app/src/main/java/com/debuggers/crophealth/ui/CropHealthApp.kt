@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
package com.debuggers.crophealth.ui

import android.app.Activity
import android.content.Intent
import android.graphics.BitmapFactory
import android.media.MediaPlayer
import android.net.Uri
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.animation.togetherWith
import androidx.compose.animation.core.tween
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.platform.testTag
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.core.view.WindowCompat
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import com.debuggers.crophealth.content.Prompt
import com.debuggers.crophealth.domain.*
import com.debuggers.crophealth.presentation.*
import com.debuggers.crophealth.inference.ImagePreparation
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlin.math.roundToInt

internal fun AppUiState.tr(en: String, kn: String) = when(language) {
    AppLanguage.ENGLISH -> en
    AppLanguage.KANNADA -> kn
    AppLanguage.HINDI -> HindiUi.translate(en)
}
private val LocalAppLanguage = staticCompositionLocalOf { AppLanguage.ENGLISH }

@Composable
fun CropHealthApp(viewModel: CropHealthViewModel) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    CropHealthScreen(state,viewModel::onAction,viewModel::text,viewModel::prompt,viewModel::newCameraFile)
}

@Composable
fun CropHealthScreen(state: AppUiState,onAction:(AppAction)->Unit,text:(String)->String,
                     prompt:(String)->Prompt,newCameraFile:()->File) {
    val context=LocalContext.current
    remember(context) { HindiUi.load(context) }
    CompositionLocalProvider(LocalAppLanguage provides state.language) {
    CropTheme {
        val activity=LocalContext.current as? Activity
        SideEffect {
            activity?.window?.let { window ->
                WindowCompat.getInsetsController(window,window.decorView).apply {
                    isAppearanceLightStatusBars=state.screen!=Screen.CAPTURE
                    isAppearanceLightNavigationBars=state.screen!=Screen.CAPTURE
                }
            }
        }
        BackHandler(enabled=state.screen!=Screen.HOME) { onAction(AppAction.Navigate(state.backScreen())) }
        AnimatedContent(
            targetState=state.screen,
            modifier=Modifier.fillMaxSize(),
            transitionSpec={
                (fadeIn(animationSpec=tween(220)) +
                    slideInVertically(animationSpec=tween(220),initialOffsetY={it/18})) togetherWith
                    (fadeOut(animationSpec=tween(160)) +
                        slideOutVertically(animationSpec=tween(160),targetOffsetY={-it/24}))
            },
            label="screen-transition",
        ) { screen ->
            if(screen==Screen.CAPTURE) {
                CameraScreen(state,onAction,newCameraFile)
            } else {
                val mainTabs=screen in listOf(Screen.HOME,Screen.HISTORY,Screen.HELP)
                val screenState=state.copy(screen=screen)
                Scaffold(
                    containerColor=Color.White,
                    topBar={if(!mainTabs && screen!=Screen.WELCOME) Header(screenState,onAction)},
                    bottomBar={if(mainTabs) BottomTabs(screenState,onAction)},
                ) { padding ->
                    Box(Modifier.fillMaxSize().padding(padding)) {
                        when(screen) {
                            Screen.WELCOME -> Welcome(state,onAction)
                            Screen.HOME -> Home(state,onAction)
                            Screen.PHOTO_REVIEW -> PhotoReview(state,onAction)
                            Screen.PROCESSING -> Processing(state)
                            Screen.RESULT -> Result(state,onAction,prompt)
                            Screen.GUIDANCE -> GuidanceScreen(state,onAction,prompt)
                            Screen.CONCERN -> ConcernScreen(state,onAction,prompt)
                            Screen.CARE_LIBRARY -> CareLibraryScreen(state,onAction)
                            Screen.HISTORY -> HistoryScreen(state,onAction)
                            Screen.HELP -> HelpScreen(state,onAction,prompt)
                            Screen.SETTINGS -> SettingsScreen(state,onAction)
                            Screen.CAPTURE -> Unit
                        }
                    }
                }
            }
        }
        state.error?.let { message ->
            AlertDialog(onDismissRequest={onAction(AppAction.DismissError)},
                title={Text(state.tr("Please try again","ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ"))},text={Text(state.tr(message,message))},
                confirmButton={TextButton(onClick={onAction(AppAction.DismissError)}) {Text(state.tr("OK","ಸರಿ"))}})
        }
    }
    }
}

@Composable private fun Header(s:AppUiState,a:(AppAction)->Unit) {
    TopAppBar(title={},navigationIcon={IconButton(onClick={a(AppAction.Navigate(s.backScreen()))}) {Icon(Icons.Outlined.ArrowBack,s.tr("Back","ಹಿಂದೆ"))}},
        actions={OfflineBadge(if(s.assessment?.evidence!=null || s.openedObservation!=null) s.tr("Analysed offline","ಆಫ್‌ಲೈನ್ ಪರಿಶೀಲನೆ") else s.tr("On this phone","ಈ ಫೋನ್‌ನಲ್ಲಿ"));Spacer(Modifier.width(20.dp))},
        colors=TopAppBarDefaults.topAppBarColors(containerColor=Color.White))
}

@Composable private fun BottomTabs(s:AppUiState,a:(AppAction)->Unit) {
    Column { HorizontalDivider(color=CropColors.Border,thickness=0.5.dp)
        Row(Modifier.fillMaxWidth().navigationBarsPadding().padding(vertical=9.dp),horizontalArrangement=Arrangement.SpaceAround) {
            listOf(Triple(Screen.HOME,Icons.Outlined.Home,s.tr("Home","ಮುಖಪುಟ")),
                Triple(Screen.HISTORY,Icons.Outlined.History,s.tr("History","ಇತಿಹಾಸ")),
                Triple(Screen.HELP,Icons.Outlined.HelpOutline,s.tr("Help","ಸಹಾಯ"))).forEach { (screen,icon,label) ->
                val selected=s.screen==screen
                Column(Modifier.width(90.dp).clip(RoundedCornerShape(14.dp)).clickable {a(AppAction.Navigate(screen))}.padding(4.dp),horizontalAlignment=Alignment.CenterHorizontally) {
                    Box(Modifier.size(38.dp).clip(RoundedCornerShape(12.dp)).background(if(selected) CropColors.Primary else CropColors.Lavender),contentAlignment=Alignment.Center) {
                        Icon(icon,label,tint=if(selected) Color.White else CropColors.Muted,modifier=Modifier.size(22.dp)) }
                    Spacer(Modifier.height(4.dp));Text(label,fontSize=11.sp,color=if(selected) CropColors.Primary else CropColors.Muted)
                }
            }
        }
    }
}

@Composable private fun OfflineBadge(label:String) {
    Row(Modifier.clip(RoundedCornerShape(20.dp)).background(Color(0xFFF0F7EF)).padding(horizontal=10.dp,vertical=6.dp),verticalAlignment=Alignment.CenterVertically) {
        Box(Modifier.size(5.dp).background(CropColors.Green,CircleShape));Spacer(Modifier.width(5.dp));Text(label,color=CropColors.Green,fontSize=10.sp)
    }
}

@Composable private fun LanguageToggle(s:AppUiState,a:(AppAction)->Unit) {
    Row(Modifier.clip(RoundedCornerShape(20.dp)).background(CropColors.Lavender).padding(3.dp)) {
        AppLanguage.entries.forEach { lang ->
            val selected=s.language==lang
            Text(lang.displayName,fontSize=11.sp,textAlign=TextAlign.Center,
                color=if(selected) CropColors.Ink else CropColors.Muted,
                modifier=Modifier.testTag("language_${lang.id}").clip(RoundedCornerShape(16.dp)).background(if(selected) Color.White else Color.Transparent)
                    .clickable {a(AppAction.SetLanguage(lang))}.widthIn(min=48.dp).padding(horizontal=8.dp,vertical=8.dp))
        }
    }
}

@Composable private fun Page(content:@Composable ColumnScope.()->Unit) {
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal=20.dp).padding(bottom=24.dp),verticalArrangement=Arrangement.spacedBy(18.dp),content=content)
}

@Composable private fun Welcome(s:AppUiState,a:(AppAction)->Unit) {
    Column(Modifier.fillMaxSize().padding(28.dp),verticalArrangement=Arrangement.Center,horizontalAlignment=Alignment.CenterHorizontally) {
        Box(Modifier.size(100.dp).background(CropColors.Lavender,CircleShape),contentAlignment=Alignment.Center) {Icon(Icons.Outlined.Grass,null,tint=CropColors.Primary,modifier=Modifier.size(54.dp))}
        Spacer(Modifier.height(28.dp));Text(s.tr("AgriScan","AgriScan"),fontSize=32.sp,fontWeight=FontWeight.Medium)
        Spacer(Modifier.height(12.dp));Text(s.tr("Care for your crops, wherever you grow.","ನೀವು ಎಲ್ಲಿದ್ದರೂ ಬೆಳೆಗಳ ಆರೈಕೆ ಮಾಡಿ."),textAlign=TextAlign.Center,color=CropColors.Muted)
        Spacer(Modifier.height(26.dp));LanguageToggle(s,a);Spacer(Modifier.height(36.dp))
        Primary(s.tr("Get started","ಪ್ರಾರಂಭಿಸಿ"),{a(AppAction.CompleteWelcome)},Icons.Outlined.ArrowForward)
    }
}

@Composable private fun Home(s:AppUiState,a:(AppAction)->Unit) {
    Page {
        Spacer(Modifier.height(8.dp))
        Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween,verticalAlignment=Alignment.CenterVertically) {OfflineBadge(s.tr("Offline ready","ಆಫ್‌ಲೈನ್ ಸಿದ್ಧ"));LanguageToggle(s,a)}
        Column(verticalArrangement=Arrangement.spacedBy(6.dp)) {
            Text(s.tr("Check your crop","ನಿಮ್ಮ ಬೆಳೆ ಪರಿಶೀಲಿಸಿ"),fontSize=30.sp,fontWeight=FontWeight.Medium)
            Text(s.tr("Take a photo of one leaf. No internet needed.","ಒಂದು ಎಲೆಯ ಫೋಟೋ ತೆಗೆಯಿರಿ. ಇಂಟರ್ನೆಟ್ ಅಗತ್ಯವಿಲ್ಲ."),color=CropColors.Muted,fontSize=13.sp)
        }
        Card(Modifier.fillMaxWidth().testTag("home_scan").clickable {a(AppAction.Navigate(Screen.CAPTURE))},shape=RoundedCornerShape(22.dp),colors=CardDefaults.cardColors(containerColor=CropColors.Primary)) {
            Column(Modifier.fillMaxWidth().height(178.dp).padding(20.dp),verticalArrangement=Arrangement.SpaceBetween) {
                Box(Modifier.size(56.dp).background(Color.White,CircleShape),contentAlignment=Alignment.Center) {Icon(Icons.Outlined.CameraAlt,null,tint=CropColors.Primary,modifier=Modifier.size(28.dp))}
                Row(Modifier.fillMaxWidth(),verticalAlignment=Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(s.tr("Scan a leaf","ಎಲೆಯನ್ನು ಪರಿಶೀಲಿಸಿ"),color=Color.White,fontSize=22.sp,fontWeight=FontWeight.Medium)
                        Spacer(Modifier.height(5.dp))
                        Text(s.tr("On your phone. In your language.","ನಿಮ್ಮ ಫೋನ್‌ನಲ್ಲಿ. ನಿಮ್ಮ ಭಾಷೆಯಲ್ಲಿ."),color=Color(0xFFDFD2F1),fontSize=11.sp)
                    }
                    Icon(Icons.Outlined.ChevronRight,null,tint=Color.White)
                }
            }
        }
        Column(verticalArrangement=Arrangement.spacedBy(10.dp)) {Section(s.tr("Choose your crop","ಬೆಳೆ ಆಯ್ಕೆಮಾಡಿ"));CropChips(s,a)}
        Secondary(s.careText("Treatment & recovery library","ಚಿಕಿತ್ಸೆ ಮತ್ತು ಚೇತರಿಕೆ ಮಾಹಿತಿ","उपचार और सुधार पुस्तकालय"),{a(AppAction.OpenCareLibrary)})
        Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween,verticalAlignment=Alignment.CenterVertically) {Section(s.tr("Recent scans","ಇತ್ತೀಚಿನ ಪರಿಶೀಲನೆಗಳು"));TextButton(onClick={a(AppAction.Navigate(Screen.HISTORY))}) {Text(s.tr("View all","ಎಲ್ಲವನ್ನೂ ನೋಡಿ"),fontSize=12.sp)}}
        if(s.observations.isEmpty()) {
            SoftCard {Icon(Icons.Outlined.History,null,tint=CropColors.Primary);Text(s.tr("Your first scan starts here","ನಿಮ್ಮ ಮೊದಲ ಪರಿಶೀಲನೆ ಇಲ್ಲಿಂದ ಪ್ರಾರಂಭವಾಗುತ್ತದೆ"),fontSize=16.sp);Text(s.tr("Saved leaf observations will appear here, only on this phone.","ಉಳಿಸಿದ ಎಲೆ ಪರಿಶೀಲನೆಗಳು ಈ ಫೋನ್‌ನಲ್ಲಿ ಮಾತ್ರ ಕಾಣಿಸುತ್ತವೆ."),fontSize=12.sp,color=CropColors.Muted)}
        } else s.observations.take(3).forEach {HistoryCard(it,s,a)}
        if(!s.model.ready) Notice(s.tr("Local model is loading or unavailable","ಸ್ಥಳೀಯ ಮಾದರಿ ಲೋಡ್ ಆಗುತ್ತಿದೆ ಅಥವಾ ಲಭ್ಯವಿಲ್ಲ"),s.tr(s.model.message,s.model.message))
    }
}

@Composable private fun CropChips(s:AppUiState,a:(AppAction)->Unit,all:Boolean=false,selected:Crop?=s.selectedCrop,onSelect:((Crop?)->Unit)?=null) {
    Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.spacedBy(8.dp)) {
        if(all) CropChip(s.tr("All","ಎಲ್ಲಾ"),selected==null,null) {onSelect?.invoke(null)}
        Crop.entries.forEach {crop ->CropChip(crop.displayName(s.language),selected==crop,crop) {if(onSelect!=null) onSelect(crop) else a(AppAction.SelectCrop(crop))}}
    }
}
@Composable private fun RowScope.CropChip(label:String,selected:Boolean,crop:Crop?,click:()->Unit) {
    Surface(modifier=Modifier.weight(1f).clip(RoundedCornerShape(15.dp)).clickable(onClick=click),shape=RoundedCornerShape(15.dp),color=if(selected) CropColors.Tomato else CropColors.Lavender) {
        Text(label,modifier=Modifier.padding(horizontal=7.dp,vertical=11.dp),fontSize=12.sp,textAlign=TextAlign.Center,color=if(selected) Color.White else CropColors.Ink,maxLines=1,overflow=TextOverflow.Ellipsis)
    }
}

@Composable private fun PhotoReview(s:AppUiState,a:(AppAction)->Unit) {
    val picker=rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) {uri ->uri?.let {a(AppAction.ImportPhoto(it))}}
    Page {
        Text(s.tr("Ready to check?","ಪರಿಶೀಲಿಸಲು ಸಿದ್ಧವೇ?"),fontSize=28.sp,fontWeight=FontWeight.Medium)
        Text(s.tr("Make sure one leaf is clear and fills the photo.","ಒಂದು ಎಲೆ ಸ್ಪಷ್ಟವಾಗಿದ್ದು ಫೋಟೋ ತುಂಬಿರುವುದನ್ನು ಖಚಿತಪಡಿಸಿಕೊಳ್ಳಿ."),fontSize=13.sp,color=CropColors.Muted)
        Photo(s.photoPath,Modifier.fillMaxWidth().height(280.dp))
        CropChips(s,a)
        SoftCard {Text(s.tr("A clearer photo helps","ಸ್ಪಷ್ಟವಾದ ಫೋಟೋ ಸಹಾಯ ಮಾಡುತ್ತದೆ"),fontSize=16.sp);Text(s.tr("Use natural light. Hold steady. Avoid several overlapping leaves.","ನೈಸರ್ಗಿಕ ಬೆಳಕು ಬಳಸಿ. ಸ್ಥಿರವಾಗಿ ಹಿಡಿಯಿರಿ. ಒಂದರ ಮೇಲೊಂದು ಎಲೆಗಳನ್ನು ತಪ್ಪಿಸಿ."),fontSize=13.sp,color=CropColors.Muted)}
        Primary(s.tr("Check this leaf","ಈ ಎಲೆಯನ್ನು ಪರಿಶೀಲಿಸಿ"),{a(AppAction.Analyze)},Icons.Outlined.Search,Modifier.testTag("analysis_button"))
        Secondary(s.tr("Retake photo","ಮತ್ತೆ ಫೋಟೋ ತೆಗೆಯಿರಿ"),{a(AppAction.Navigate(Screen.CAPTURE))},Icons.Outlined.CameraAlt)
        TextButton(onClick={picker.launch("image/*")},modifier=Modifier.align(Alignment.CenterHorizontally)) {Text(s.tr("Choose another photo","ಬೇರೆ ಫೋಟೋ ಆಯ್ಕೆಮಾಡಿ"))}
    }
}

@Composable private fun Processing(s:AppUiState) {
    Column(Modifier.fillMaxSize().padding(30.dp),verticalArrangement=Arrangement.Center,horizontalAlignment=Alignment.CenterHorizontally) {
        CircularProgressIndicator(color=CropColors.Primary,strokeWidth=3.dp);Spacer(Modifier.height(24.dp))
        Text(s.tr("Checking your leaf","ಎಲೆಯನ್ನು ಪರಿಶೀಲಿಸಲಾಗುತ್ತಿದೆ"),fontSize=25.sp,fontWeight=FontWeight.Medium)
        Spacer(Modifier.height(12.dp));Text(s.tr("The assessment stays on this phone.","ಪರಿಶೀಲನೆ ಈ ಫೋನ್‌ನಲ್ಲೇ ನಡೆಯುತ್ತದೆ."),textAlign=TextAlign.Center,color=CropColors.Muted)
    }
}

@Composable private fun Result(s:AppUiState,a:(AppAction)->Unit,prompt:(String)->Prompt) {
    val result=s.assessment;val evidence=result?.evidence
    val stored=s.openedObservation
    // Result types come from the engine's acceptance policy. Dataset-tested
    // prototype acceptance and independent field validation are separate facts.
    val accepted=result is AssessmentResult.LikelyCondition || result is AssessmentResult.HealthyLooking || stored?.isAcceptedModelMatch()==true
    val fieldValidated=evidence?.calibratedAndValidated ?: stored?.validated ?: false
    val top=evidence?.ranked?.firstOrNull()
    val unsupported=result?.rejectsUnsupportedInput()==true || stored?.hidesUnsupportedCandidate()==true
    val uncertainCandidate=result?.hasLeafCheckedCandidate()==true || stored?.isLeafCheckedCandidate()==true
    val noLeaf=(result as? AssessmentResult.Retake)?.quality?.issues?.contains(QualityIssue.NOT_A_LEAF)==true
    val condition=if(unsupported) null else top?.condition ?: stored?.conditionId?.let(Conditions::byId)
    val cropMismatch=result is AssessmentResult.CropMismatch || stored?.resultType=="crop_mismatch"
    val prediction=((result is AssessmentResult.Uncertain || result is AssessmentResult.CropMismatch) &&
        evidence?.sourceEvaluated==true && condition!=null &&
        (result !is AssessmentResult.Uncertain || (UncertaintyReason.MODEL_NOT_VALIDATED !in result.reasons && !unsupported))) ||
        stored?.isPrototypePrediction(s)==true
    val isRetake=result is AssessmentResult.Retake
    val unavailable=result is AssessmentResult.ModelUnavailable
    val title=when {
        noLeaf ->s.predictionText("No clear leaf detected","ಸ್ಪಷ್ಟ ಎಲೆ ಪತ್ತೆಯಾಗಲಿಲ್ಲ","साफ़ पत्ती नहीं मिली")
        isRetake ->s.tr("Let's take another photo","ಇನ್ನೊಂದು ಫೋಟೋ ತೆಗೆಯೋಣ")
        unavailable ->s.tr("Assessment unavailable","ಪರಿಶೀಲನೆ ಲಭ್ಯವಿಲ್ಲ")
        accepted || prediction ->condition?.displayName(s.language) ?: s.tr("Leaf assessment","ಎಲೆಯ ಪರಿಶೀಲನೆ")
        cropMismatch ->s.tr("Check the selected crop","ಆಯ್ಕೆ ಮಾಡಿದ ಬೆಳೆ ಪರಿಶೀಲಿಸಿ")
        else ->s.tr("Not sure about this one","ಈ ಫೋಟೋದ ಬಗ್ಗೆ ಖಚಿತವಿಲ್ಲ")
    }
    Page {
        if(!accepted && !prediction) Notice(title,when {
            noLeaf ->s.predictionText("Take a close photo of one crop leaf. Objects and animals cannot be diagnosed.","ಒಂದು ಬೆಳೆ ಎಲೆಯ ಹತ್ತಿರದ ಫೋಟೋ ತೆಗೆಯಿರಿ. ವಸ್ತುಗಳು ಮತ್ತು ಪ್ರಾಣಿಗಳ ರೋಗನಿರ್ಣಯ ಸಾಧ್ಯವಿಲ್ಲ.","फसल की एक पत्ती की नज़दीकी तस्वीर लें। वस्तुओं और जानवरों में फसल रोग नहीं पहचान सकते।")
            isRetake ->s.tr("Try a brighter, sharper close-up of one leaf.","ಒಂದು ಎಲೆಯ ಹೆಚ್ಚು ಬೆಳಕಿನ ಸ್ಪಷ್ಟ ಫೋಟೋ ತೆಗೆಯಿರಿ.")
            unavailable ->s.tr("No diagnosis was produced. Your photo stays on this phone.","ಯಾವುದೇ ರೋಗನಿರ್ಣಯ ಮಾಡಲಾಗಿಲ್ಲ. ಫೋಟೋ ಈ ಫೋನ್‌ನಲ್ಲೇ ಉಳಿಯುತ್ತದೆ.")
            cropMismatch ->s.tr("The model candidate and selected crop differ. Please check and retake.","ಮಾದರಿಯ ಊಹೆ ಮತ್ತು ಆಯ್ಕೆ ಮಾಡಿದ ಬೆಳೆ ಬೇರೆ ಇವೆ. ಪರಿಶೀಲಿಸಿ ಮತ್ತೆ ಫೋಟೋ ತೆಗೆಯಿರಿ.")
            else ->s.tr("These are possible matches, not a confirmed diagnosis. Ask a local crop expert when needed.","ಇವು ಸಾಧ್ಯತೆಗಳು ಮಾತ್ರ, ದೃಢಪಟ್ಟ ರೋಗನಿರ್ಣಯವಲ್ಲ. ಅಗತ್ಯವಿದ್ದರೆ ಸ್ಥಳೀಯ ಕೃಷಿ ತಜ್ಞರನ್ನು ಸಂಪರ್ಕಿಸಿ.")
        })
        Row(verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(14.dp)) {
            Photo(s.photoPath,Modifier.size(82.dp),256);Column(Modifier.weight(1f)) {
                Text((if(prediction) condition?.crop else null)?.displayName(s.language) ?: s.selectedCrop.displayName(s.language),color=CropColors.Muted,fontSize=12.sp)
                if(prediction) Text(if(uncertainCandidate) s.predictionText("Uncertain model candidate","ಅನಿಶ್ಚಿತ ಮಾದರಿ ಸಾಧ್ಯತೆ","मॉडल का अनिश्चित अनुमान") else s.predictionText("Predicted condition","ಊಹಿಸಿದ ಸ್ಥಿತಿ","अनुमानित स्थिति"),color=CropColors.Muted,fontSize=12.sp)
                Text(if(accepted || prediction) title else s.tr("Leaf observation","ಎಲೆಯ ವೀಕ್ಷಣೆ"),fontSize=24.sp,fontWeight=FontWeight.Medium)
            }
        }
        if(prediction && cropMismatch) Notice(s.predictionText("Crop mismatch","ಬೆಳೆ ಹೊಂದಿಕೆಯಾಗುತ್ತಿಲ್ಲ","फसल का मेल नहीं है"),
            s.predictionText("Selected crop: ","ಆಯ್ಕೆ ಮಾಡಿದ ಬೆಳೆ: ","चुनी हुई फसल: ")+s.selectedCrop.displayName(s.language)+". "+
            s.predictionText("Model predicts: ","ಮಾದರಿಯ ಊಹೆ: ","मॉडल का अनुमान: ")+(condition?.crop?.displayName(s.language) ?: "")+". "+
            s.predictionText("Check the crop selection or retake the photo.","ಬೆಳೆ ಆಯ್ಕೆಯನ್ನು ಪರಿಶೀಲಿಸಿ ಅಥವಾ ಮತ್ತೆ ಚಿತ್ರ ತೆಗೆಯಿರಿ.","फसल का चयन जाँचें या फिर से तस्वीर लें।"))
        if(prediction && !cropMismatch) Notice(s.predictionText("Low confidence","ಕಡಿಮೆ ವಿಶ್ವಾಸ","कम भरोसा"),s.predictionText(
            "The model is unsure. Retake a close photo of one leaf in daylight, keeping it sharp and filling most of the frame. Check with a crop expert before choosing treatment.",
            "ಮಾದರಿಗೆ ಖಚಿತತೆ ಇಲ್ಲ. ಹಗಲಿನ ಬೆಳಕಿನಲ್ಲಿ ಒಂದೇ ಎಲೆಯ ಹತ್ತಿರದ, ಸ್ಪಷ್ಟ ಚಿತ್ರ ತೆಗೆಯಿರಿ; ಎಲೆಯನ್ನು ಚಿತ್ರದ ಹೆಚ್ಚಿನ ಭಾಗದಲ್ಲಿ ಇರಿಸಿ. ಚಿಕಿತ್ಸೆ ಆಯ್ಕೆ ಮಾಡುವ ಮೊದಲು ಕೃಷಿ ತಜ್ಞರನ್ನು ಸಂಪರ್ಕಿಸಿ.",
            "मॉडल को यक़ीन नहीं है। दिन की रोशनी में एक पत्ती की साफ़, नज़दीकी तस्वीर लें और पत्ती को फ़्रेम में बड़ा रखें। उपचार चुनने से पहले कृषि विशेषज्ञ से पूछें।"))
        val score=if(unsupported) null else top?.score ?: stored?.score
        if(score!=null) ScoreCard(s,score,fieldValidated,accepted,prediction)
        if(accepted && !fieldValidated) Text(s.tr("Dataset-tested estimate. Confirm the condition with a local crop expert.","ಡೇಟಾಸೆಟ್‌ನಲ್ಲಿ ಪರೀಕ್ಷಿಸಿದ ಅಂದಾಜು. ಸ್ಥಳೀಯ ಕೃಷಿ ತಜ್ಞರಿಂದ ಸ್ಥಿತಿಯನ್ನು ಖಚಿತಪಡಿಸಿಕೊಳ್ಳಿ."),fontSize=12.sp,color=CropColors.Muted)
        if(!accepted && !unsupported && (evidence?.ranked?.isNotEmpty()==true || condition!=null)) SoftCard {
            Text(if(prediction) s.predictionText("Model predictions","ಮಾದರಿಯ ಊಹೆಗಳು","मॉडल के अनुमान") else s.tr("Possible — not confirmed","ಸಾಧ್ಯತೆ — ದೃಢಪಟ್ಟಿಲ್ಲ"),fontSize=15.sp,fontWeight=FontWeight.Medium)
            val ranked=evidence?.ranked?.take(3)
            val candidateIds=ranked?.map { it.condition.id }.orEmpty()
            if(candidateIds.containsAll(listOf("tomato_early_blight","tomato_target_spot"))) Text(
                s.predictionText("These tomato candidates can look alike: brown leaf spots (early blight or target spot). The photo does not distinguish them reliably.",
                    "ಈ ಟೊಮ್ಯಾಟೊ ಸ್ಥಿತಿಗಳು ಒಂದೇ ರೀತಿಯಾಗಿ ಕಾಣಬಹುದು: ಕಂದು ಎಲೆ ಚುಕ್ಕೆಗಳು (ಆರಂಭಿಕ ಅಂಗಮಾರಿ ಅಥವಾ ಗುರಿ ಆಕಾರದ ಚುಕ್ಕೆ). ಈ ಚಿತ್ರದಿಂದ ಅವುಗಳನ್ನು ಖಚಿತವಾಗಿ ಬೇರ್ಪಡಿಸಲಾಗುವುದಿಲ್ಲ.",
                    "टमाटर की ये स्थितियाँ मिलती-जुलती दिख सकती हैं: भूरे पत्ती धब्बे (अर्ली ब्लाइट या टार्गेट स्पॉट)। यह तस्वीर दोनों में भरोसेमंद अंतर नहीं बता पाती।"),
                fontSize=12.sp,color=CropColors.Muted)
            if(ranked!=null) ranked.forEach {PredictionRow(it.condition.displayName(s.language),it.score)}
            else condition?.let {Text(it.displayName(s.language),fontSize=16.sp)}
        }
        if(result is AssessmentResult.Retake) SoftCard {Text(s.tr("Photo checks","ಫೋಟೋ ಪರಿಶೀಲನೆ"),fontSize=16.sp);result.quality.issues.forEach {Text("• "+qualityCopy(it,s),fontSize=13.sp,color=CropColors.Muted)}}
        if(accepted || prediction) Row(horizontalArrangement=Arrangement.spacedBy(10.dp)) {
            MiniCard(s.tr("Concern check","ಲಕ್ಷಣ ಪರಿಶೀಲನೆ"),s.careText("6 observation questions","6 ವೀಕ್ಷಣೆ ಪ್ರಶ್ನೆಗಳು","लक्षणों के 6 प्रश्न"),Modifier.weight(1f))
            MiniCard(s.tr("Other signs?","ಬೇರೆ ಲಕ್ಷಣಗಳಿವೆಯೇ?"),s.tr("Check with an expert","ತಜ್ಞರನ್ನು ಸಂಪರ್ಕಿಸಿ"),Modifier.weight(1f))
        }
        if(s.symptomsComplete) AdvisorySummary(s,reasons=false)
        AudioButton(s.prompt?.audioAsset ?: prompt("uncertain").audioAsset,s.tr("Listen in ${s.language.displayName}","ಕನ್ನಡದಲ್ಲಿ ಕೇಳಿ"),autoPlay=s.autoAudio)
        if(accepted || prediction) {
            if(cropMismatch) Secondary(s.predictionText("Change selected crop","ಆಯ್ಕೆ ಮಾಡಿದ ಬೆಳೆ ಬದಲಿಸಿ","चुनी हुई फसल बदलें"),{a(AppAction.Navigate(Screen.HOME))})
            Primary(s.careText("Assess severity · 6 questions","ತೀವ್ರತೆ ಪರಿಶೀಲಿಸಿ · 6 ಪ್ರಶ್ನೆಗಳು","गंभीरता जाँचें · 6 प्रश्न"),{a(AppAction.Navigate(Screen.CONCERN))})
            if(prediction) Secondary(s.tr("Retake photo","ಮತ್ತೆ ಫೋಟೋ ತೆಗೆಯಿರಿ"),{a(AppAction.Navigate(Screen.CAPTURE))},Icons.Outlined.CameraAlt)
        } else {
            ExpertCall(s)
            Primary(s.tr("Retake photo","ಮತ್ತೆ ಫೋಟೋ ತೆಗೆಯಿರಿ"),{a(AppAction.Navigate(Screen.CAPTURE))},Icons.Outlined.CameraAlt)
            Secondary(s.careText("Assess symptoms · 6 questions","ಲಕ್ಷಣ ಪರಿಶೀಲಿಸಿ · 6 ಪ್ರಶ್ನೆಗಳು","लक्षण जाँचें · 6 प्रश्न"),{a(AppAction.Navigate(Screen.CONCERN))})
        }
        if(stored==null) Secondary(if(s.savedObservationId==null) s.tr("Save scan","ಪರಿಶೀಲನೆ ಉಳಿಸಿ") else s.tr("Saved on this phone","ಈ ಫೋನ್‌ನಲ್ಲಿ ಉಳಿಸಲಾಗಿದೆ"),{a(AppAction.SaveObservation)},Icons.Outlined.BookmarkBorder,enabled=s.savedObservationId==null && result!=null)
        Secondary(s.careText("Browse treatment & recovery library","ಚಿಕಿತ್ಸೆ ಮತ್ತು ಚೇತರಿಕೆ ಮಾಹಿತಿ ನೋಡಿ","उपचार और सुधार पुस्तकालय देखें"),{a(AppAction.OpenCareLibrary)})
        Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.Center) {TextButton(onClick={a(AppAction.ShareCurrent)}) {Icon(Icons.Outlined.Share,null,Modifier.size(16.dp));Spacer(Modifier.width(6.dp));Text(s.tr("Share observation","ವೀಕ್ಷಣೆ ಹಂಚಿಕೊಳ್ಳಿ"))}}
        if(!accepted && !prediction) Text(s.tr("Prototype model: scores are not validated diagnostic probabilities.","ಪ್ರಾಯೋಗಿಕ ಮಾದರಿ: ಅಂಕಗಳು ದೃಢೀಕರಿಸಿದ ರೋಗನಿರ್ಣಯದ ಸಂಭವನೀಯತೆಗಳಲ್ಲ."),fontSize=11.sp,color=CropColors.Muted)
    }
}

@Composable private fun ScoreCard(s:AppUiState,score:Float,fieldValidated:Boolean,accepted:Boolean,prediction:Boolean=false) {
    SoftCard {
        Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween) {Text(when {fieldValidated->s.tr("Model confidence","ಮಾದರಿಯ ವಿಶ್ವಾಸ");accepted->s.tr("Model match score","ಮಾದರಿಯ ಹೊಂದಾಣಿಕೆ ಅಂಕ");prediction->s.predictionText("Prediction score","ಊಹೆಯ ಅಂಕ","अनुमान का अंक");else->s.tr("Model score · unvalidated","ಮಾದರಿಯ ಅಂಕ · ದೃಢೀಕರಿಸಿಲ್ಲ")},fontSize=13.sp);Text("${(score.coerceIn(0f,1f)*100).roundToInt()}%",fontSize=17.sp,fontWeight=FontWeight.Medium)}
        LinearProgressIndicator(progress={score.coerceIn(0f,1f)},modifier=Modifier.fillMaxWidth().height(6.dp).clip(CircleShape),color=if(fieldValidated) CropColors.Green else CropColors.Gold,trackColor=CropColors.Border)
    }
}
@Composable private fun PredictionRow(label:String,score:Float) {Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween) {Text(label,Modifier.weight(1f),fontSize=14.sp);Text("${(score*100).roundToInt()}%",fontSize=13.sp,color=CropColors.Muted)}}
private fun qualityCopy(issue:QualityIssue,s:AppUiState)=when(issue) {QualityIssue.BLURRY->s.tr("Hold steady and focus on one leaf.","ಸ್ಥಿರವಾಗಿ ಹಿಡಿದು ಒಂದು ಎಲೆಯ ಮೇಲೆ ಕೇಂದ್ರೀಕರಿಸಿ.");QualityIssue.TOO_DARK->s.tr("Move into natural light.","ನೈಸರ್ಗಿಕ ಬೆಳಕಿಗೆ ಸರಿಸಿ.");QualityIssue.TOO_BRIGHT->s.tr("Avoid glare or direct flash.","ಪ್ರಖರ ಬೆಳಕು ಅಥವಾ ನೇರ ಫ್ಲ್ಯಾಶ್ ತಪ್ಪಿಸಿ.");QualityIssue.TOO_SMALL->s.tr("Choose a larger, closer photo.","ದೊಡ್ಡದಾದ ಹತ್ತಿರದ ಫೋಟೋ ಆಯ್ಕೆಮಾಡಿ.");QualityIssue.UNREADABLE->s.tr("This image could not be opened.","ಈ ಚಿತ್ರವನ್ನು ತೆರೆಯಲಾಗಲಿಲ್ಲ.");QualityIssue.NOT_A_LEAF->s.predictionText("No crop leaf detected. Photograph one crop leaf.","ಬೆಳೆ ಎಲೆ ಪತ್ತೆಯಾಗಲಿಲ್ಲ. ಒಂದು ಬೆಳೆ ಎಲೆಯ ಫೋಟೋ ತೆಗೆಯಿರಿ.","फसल की पत्ती नहीं मिली। एक पत्ती की तस्वीर लें।")}

internal fun AppUiState.careText(en: String, kn: String, hi: String): String = when (language) {
    AppLanguage.ENGLISH -> en; AppLanguage.KANNADA -> kn; AppLanguage.HINDI -> hi
}

@Composable private fun AdvisorySummary(s:AppUiState, reasons:Boolean=true) {
    val model=s.advisory
    val severity=when(model.severity) {
        ReportedSeverity.NONE ->s.careText("No visible damage reported","ಕಾಣುವ ಹಾನಿ ತಿಳಿಸಿಲ್ಲ","कोई दिखने वाला नुकसान नहीं बताया")
        ReportedSeverity.MILD ->s.careText("Mild damage","ಕಡಿಮೆ ಹಾನಿ","हल्का नुकसान")
        ReportedSeverity.MODERATE ->s.careText("Moderate damage","ಮಧ್ಯಮ ಹಾನಿ","मध्यम नुकसान")
        ReportedSeverity.SEVERE ->s.careText("Severe signs","ತೀವ್ರ ಲಕ್ಷಣಗಳು","गंभीर लक्षण")
        ReportedSeverity.UNKNOWN ->s.careText("Not enough information","ಮಾಹಿತಿ ಸಾಕಾಗಿಲ್ಲ","जानकारी पर्याप्त नहीं")
    }
    val urgency=when(model.urgency) {
        CareUrgency.URGENT ->s.careText("Urgent · contact an expert now","ತುರ್ತು · ಈಗಲೇ ತಜ್ಞರನ್ನು ಸಂಪರ್ಕಿಸಿ","तुरंत विशेषज्ञ से संपर्क करें")
        CareUrgency.SAME_DAY ->s.careText("Get advice today · within 24 hours","ಇಂದೇ ಸಲಹೆ ಪಡೆಯಿರಿ · 24 ಗಂಟೆಯೊಳಗೆ","आज सलाह लें · 24 घंटे के भीतर")
        CareUrgency.SOON ->s.careText("Ask an expert within 48 hours","48 ಗಂಟೆಯೊಳಗೆ ತಜ್ಞರನ್ನು ಕೇಳಿ","48 घंटे में विशेषज्ञ से पूछें")
        CareUrgency.MONITOR ->s.careText("Monitor · recheck within 48 hours","ಗಮನಿಸಿ · 48 ಗಂಟೆಯೊಳಗೆ ಪರಿಶೀಲಿಸಿ","निगरानी करें · 48 घंटे में दोबारा देखें")
    }
    val color=when(model.urgency) {CareUrgency.URGENT->CropColors.Rose;CareUrgency.SAME_DAY,CareUrgency.SOON->CropColors.Gold;else->CropColors.Green}
    Surface(shape=RoundedCornerShape(20.dp),color=CropColors.Lavender,modifier=Modifier.fillMaxWidth().testTag("advisory_summary")) {
        Column(Modifier.padding(18.dp),verticalArrangement=Arrangement.spacedBy(10.dp)) {
            Text(s.careText("Care & urgency","ಆರೈಕೆ ಮತ್ತು ತುರ್ತು ಕ್ರಮ","देखभाल और तात्कालिकता"),fontSize=20.sp,fontWeight=FontWeight.Medium)
            Text(s.careText("Reported damage","ತಿಳಿಸಿದ ಹಾನಿ","बताया गया नुकसान"),fontSize=12.sp,color=CropColors.Muted)
            Text(severity,modifier=Modifier.testTag("advisory_severity"),fontSize=19.sp,fontWeight=FontWeight.Medium)
            HorizontalDivider(color=CropColors.Border)
            Text(s.careText("When to act","ಯಾವಾಗ ಕ್ರಮ ಕೈಗೊಳ್ಳಬೇಕು","कब कदम उठाएँ"),fontSize=12.sp,color=CropColors.Muted)
            Text(urgency,modifier=Modifier.testTag("advisory_urgency"),fontSize=17.sp,color=color,fontWeight=FontWeight.Medium)
            if(reasons) model.reasonCodes.forEach { code -> Text("• "+careReason(code,s),fontSize=13.sp,color=CropColors.Muted) }
            Text(s.careText("Based on your answers, not a measured percentage or the disease model score.","ನಿಮ್ಮ ಉತ್ತರಗಳ ಆಧಾರಿತ; ಅಳೆಯಲಾದ ಶೇಕಡಾವಾರು ಅಥವಾ ರೋಗ ಮಾದರಿಯ ಅಂಕವಲ್ಲ.","आपके उत्तरों पर आधारित; यह मापा गया प्रतिशत या रोग मॉडल का अंक नहीं है।"),fontSize=11.sp,color=CropColors.Muted)
        }
    }
    AdvisoryAudio(s,"advisory_"+model.urgency.name.lowercase(Locale.ROOT),s.careText("Listen to urgency advice","ತುರ್ತು ಸಲಹೆ ಕೇಳಿ","तात्कालिक सलाह सुनें"))
}

@Composable private fun AdvisoryAudio(s:AppUiState,name:String,label:String) {
    val context=LocalContext.current
    val path="audio/${s.language.id}/$name.ogg"
    val available=remember(path) {runCatching {context.assets.openFd(path).use { }}.isSuccess}
    if(available) AudioButton(path,label)
}

private fun careReason(code:String,s:AppUiState):String=when(code) {
    "awaiting_answers" ->s.careText("Answer the questions to assess reported damage.","ಹಾನಿ ಪರಿಶೀಲಿಸಲು ಪ್ರಶ್ನೆಗಳಿಗೆ ಉತ್ತರಿಸಿ.","नुकसान का आकलन करने के लिए प्रश्नों के उत्तर दें।")
    "coverage_unknown" ->s.careText("The affected leaf area is not known.","ಪೀಡಿತ ಎಲೆಯ ಭಾಗ ತಿಳಿದಿಲ್ಲ.","पत्ती का प्रभावित हिस्सा पता नहीं है।")
    "coverage_none" ->s.careText("No visible leaf damage was reported.","ಕಾಣುವ ಎಲೆ ಹಾನಿ ತಿಳಿಸಿಲ್ಲ.","पत्ती पर दिखने वाला नुकसान नहीं बताया।")
    "coverage_low" ->s.careText("You reported less than 10% of this leaf affected.","ಈ ಎಲೆಯ 10% ಕ್ಕಿಂತ ಕಡಿಮೆ ಭಾಗ ಪೀಡಿತ ಎಂದಿದ್ದೀರಿ.","आपने इस पत्ते का 10% से कम प्रभावित बताया।")
    "coverage_moderate" ->s.careText("You reported about 10–30% of this leaf affected.","ಈ ಎಲೆಯ ಸುಮಾರು 10–30% ಭಾಗ ಪೀಡಿತ ಎಂದಿದ್ದೀರಿ.","आपने इस पत्ते का लगभग 10–30% प्रभावित बताया।")
    "coverage_high" ->s.careText("You reported more than 30% of this leaf affected.","ಈ ಎಲೆಯ 30% ಕ್ಕಿಂತ ಹೆಚ್ಚು ಭಾಗ ಪೀಡಿತ ಎಂದಿದ್ದೀರಿ.","आपने इस पत्ते का 30% से अधिक प्रभावित बताया।")
    "wilting" ->s.careText("Wilting or dying plants need immediate attention.","ಬಾಡುವ ಅಥವಾ ಸಾಯುವ ಗಿಡಗಳಿಗೆ ತಕ್ಷಣ ಗಮನ ಬೇಕು.","मुरझाते या मरते पौधों को तुरंत ध्यान चाहिए।")
    "fruit_or_stem" ->s.careText("Fruit, tuber or stem symptoms may threaten the harvest.","ಹಣ್ಣು, ಗೆಡ್ಡೆ ಅಥವಾ ಕಾಂಡದ ಲಕ್ಷಣ ಇಳುವರಿಗೆ ಹಾನಿ ಮಾಡಬಹುದು.","फल, कंद या तने के लक्षण उपज को नुकसान पहुँचा सकते हैं।")
    "rapid_spread" ->s.careText("Symptoms are spreading quickly.","ಲಕ್ಷಣಗಳು ವೇಗವಾಗಿ ಹರಡುತ್ತಿವೆ.","लक्षण तेजी से फैल रहे हैं।")
    "multiple_plants" ->s.careText("Many plants are affected.","ಅನೇಕ ಸಸ್ಯಗಳು ಪೀಡಿತವಾಗಿವೆ.","कई पौधे प्रभावित हैं।")
    "uncertain_answers" ->s.careText("Some answers are uncertain; get the crop checked.","ಕೆಲವು ಉತ್ತರ ಖಚಿತವಿಲ್ಲ; ಬೆಳೆ ಪರಿಶೀಲಿಸಿಕೊಳ್ಳಿ.","कुछ उत्तर अनिश्चित हैं; फसल की जाँच कराएँ।")
    "wet_weather" ->s.careText("Wet conditions can favor leaf disease; inspect nearby plants.","ತೇವ ಎಲೆ ರೋಗಕ್ಕೆ ಅನುಕೂಲ; ಹತ್ತಿರದ ಗಿಡಗಳನ್ನು ಪರಿಶೀಲಿಸಿ.","नमी पत्ती रोग बढ़ा सकती है; आसपास के पौधे जाँचें।")
    "rapid_blight" ->s.careText("Suspected late blight can spread rapidly; get advice today.","ಶಂಕಿತ ತಡವಾದ ಅಂಗಮಾರಿ ವೇಗವಾಗಿ ಹರಡಬಹುದು; ಇಂದೇ ಸಲಹೆ ಪಡೆಯಿರಿ.","संभावित पछेती झुलसा तेजी से फैल सकता है; आज ही सलाह लें।")
    "virus" ->s.careText("Confirm suspected virus symptoms; sprays do not cure a virus.","ಶಂಕಿತ ವೈರಸ್ ಲಕ್ಷಣ ದೃಢಪಡಿಸಿ; ಸಿಂಪಡಣೆ ವೈರಸ್ ಗುಣಪಡಿಸುವುದಿಲ್ಲ.","संभावित विषाणु लक्षणों की पुष्टि कराएँ; छिड़काव विषाणु नहीं मिटाता।")
    "healthy_conflict" ->s.careText("Your symptoms conflict with the healthy-looking prediction. Confirm the cause.","ನಿಮ್ಮ ಲಕ್ಷಣ ಆರೋಗ್ಯಕರ ಅಂದಾಜಿಗೆ ಹೊಂದುವುದಿಲ್ಲ. ಕಾರಣ ದೃಢಪಡಿಸಿ.","आपके लक्षण स्वस्थ दिखने के अनुमान से मेल नहीं खाते। कारण की पुष्टि कराएँ।")
    else ->s.careText("Confirm the cause with a local agriculture expert.","ಸ್ಥಳೀಯ ಕೃಷಿ ತಜ್ಞರಿಂದ ಕಾರಣ ದೃಢಪಡಿಸಿ.","स्थानीय कृषि विशेषज्ञ से कारण की पुष्टि कराएँ।")
}

@Composable private fun CareLibraryScreen(s:AppUiState,a:(AppAction)->Unit) {
    var crop by rememberSaveable {mutableStateOf<String?>(null)}
    var query by rememberSaveable {mutableStateOf("")}
    val entries=Conditions.all.filter { (crop==null || it.crop.id==crop) &&
        (query.isBlank() || it.displayName(s.language).contains(query,ignoreCase=true) || it.nameEn.contains(query,ignoreCase=true)) }
    Page {
        LanguageToggle(s,a)
        Text(s.careText("Treatment & recovery library","ಚಿಕಿತ್ಸೆ ಮತ್ತು ಚೇತರಿಕೆ ಮಾಹಿತಿ","उपचार और सुधार पुस्तकालय"),fontSize=28.sp,fontWeight=FontWeight.Medium)
        Text(s.careText("Choose a condition, answer six questions, then review its treatment and recovery plan. A library selection is not a diagnosis.","ಸ್ಥಿತಿ ಆಯ್ಕೆಮಾಡಿ, ಆರು ಪ್ರಶ್ನೆಗಳಿಗೆ ಉತ್ತರಿಸಿ, ನಂತರ ಚಿಕಿತ್ಸೆಯ ಮತ್ತು ಚೇತರಿಕೆಯ ಯೋಜನೆ ನೋಡಿ. ಗ್ರಂಥಾಲಯದ ಆಯ್ಕೆ ರೋಗನಿರ್ಣಯವಲ್ಲ.","स्थिति चुनें, छह सवालों के जवाब दें, फिर उपचार और सुधार योजना देखें। पुस्तकालय में चयन रोग की पुष्टि नहीं है।"),fontSize=13.sp,color=CropColors.Muted)
        CropChips(s,a,all=true,selected=Crop.entries.firstOrNull {it.id==crop},onSelect={crop=it?.id})
        OutlinedTextField(value=query,onValueChange={query=it},label={Text(s.careText("Search a condition","ಸ್ಥಿತಿ ಹುಡುಕಿ","स्थिति खोजें"))},singleLine=true,modifier=Modifier.fillMaxWidth().testTag("care_library_search"))
        if(entries.isEmpty()) Text(s.careText("No matching conditions. Try another crop or search.","ಹೊಂದುವ ಸ್ಥಿತಿ ಇಲ್ಲ. ಬೇರೆ ಬೆಳೆ ಅಥವಾ ಪದ ಹುಡುಕಿ.","कोई मिलती स्थिति नहीं। दूसरी फसल या खोज आजमाएँ।"))
        entries.forEach {condition ->
            Surface(onClick={a(AppAction.SelectCareCondition(condition.id))},shape=RoundedCornerShape(18.dp),
                color=CropColors.Lavender,modifier=Modifier.fillMaxWidth().testTag("care_library_"+condition.id)) {
                Row(Modifier.padding(16.dp),verticalAlignment=Alignment.CenterVertically) {
                    Column(Modifier.weight(1f),verticalArrangement=Arrangement.spacedBy(4.dp)) {
                        Text(condition.displayName(s.language),fontSize=17.sp,fontWeight=FontWeight.Medium)
                        Text(condition.crop.displayName(s.language),fontSize=12.sp,color=CropColors.Muted)
                    }
                    Icon(Icons.Outlined.ChevronRight,null,tint=CropColors.Primary)
                }
            }
        }
    }
}

@Composable private fun GuidanceScreen(s:AppUiState,a:(AppAction)->Unit,prompt:(String)->Prompt) {
    val profile=s.advisoryProfile
    val protocol=s.careProtocol
    val conditionId=protocol?.conditionId ?: s.manualCare?.conditionId ?: profile?.conditionId
    Page {
        Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.End) {LanguageToggle(s,a)}
        Text(s.careText("Treatment & recovery plan","ಚಿಕಿತ್ಸೆ ಮತ್ತು ಚೇತರಿಕೆ ಯೋಜನೆ","उपचार और सुधार योजना"),fontSize=28.sp,fontWeight=FontWeight.Medium)
        conditionId?.let {id -> Conditions.byId(id)?.let {condition ->
            Text(condition.displayName(s.language),fontSize=22.sp,fontWeight=FontWeight.Medium,modifier=Modifier.testTag("care_condition_name"))
            Text(condition.crop.displayName(s.language),fontSize=13.sp,color=CropColors.Muted)
        } }
        if(!s.careSymptomsComplete) {
            Notice(s.careText("Check damage before viewing care and urgency","ಆರೈಕೆ ಮತ್ತು ತುರ್ತು ಕ್ರಮ ನೋಡುವ ಮೊದಲು ಹಾನಿ ಪರಿಶೀಲಿಸಿ","देखभाल और तात्कालिकता देखने से पहले नुकसान जाँचें"),s.careText("Answer the six questions about what you see on the crop first.","ಬೆಳೆಯಲ್ಲಿ ನೀವು ಗಮನಿಸಿದುದರ ಕುರಿತು ಆರು ಪ್ರಶ್ನೆಗಳಿಗೆ ಮೊದಲು ಉತ್ತರಿಸಿ.","पहले फसल पर दिख रहे लक्षणों के बारे में छह सवालों के जवाब दें।"))
            Primary(s.careText("Check damage & urgency · 6 questions","ಹಾನಿ ಮತ್ತು ತುರ್ತು ಪರಿಶೀಲನೆ · 6 ಪ್ರಶ್ನೆಗಳು","नुकसान और तात्कालिकता जाँचें · 6 प्रश्न"),{a(AppAction.Navigate(Screen.CONCERN))})
        } else {
            if(s.manualCare!=null) Notice(s.careText("Selected by you — care library","ನೀವು ಆಯ್ಕೆಮಾಡಿದ್ದು — ಆರೈಕೆ ಮಾಹಿತಿ","आपके द्वारा चुना गया — देखभाल पुस्तकालय"),s.careText("This selection does not change the photo prediction or saved scan. Confirm the cause before disease-specific treatment.","ಈ ಆಯ್ಕೆ ಚಿತ್ರ ಅಂದಾಜು ಅಥವಾ ಉಳಿಸಿದ ದಾಖಲೆಯನ್ನು ಬದಲಿಸುವುದಿಲ್ಲ. ನಿರ್ದಿಷ್ಟ ಚಿಕಿತ್ಸೆಗೆ ಮೊದಲು ಕಾರಣ ದೃಢಪಡಿಸಿ.","यह चयन तस्वीर के अनुमान या सहेजे स्कैन को नहीं बदलता। रोग विशेष के उपचार से पहले कारण की पुष्टि करें।"))
            AdvisorySummary(s)
            Primary(s.careText("Review the six answers","ಆರು ಉತ್ತರ ಪರಿಶೀಲಿಸಿ","छह उत्तरों की समीक्षा करें"),{a(AppAction.Navigate(Screen.CONCERN))})
            if(profile!=null) {
                Notice(s.careText("If this condition is confirmed","ಈ ಸ್ಥಿತಿ ದೃಢಪಟ್ಟರೆ","यदि इस स्थिति की पुष्टि हो"),profile.copy.curability)
                AdvisoryAudio(s,"advisory_"+profile.conditionId,s.careText("Listen to general care summary","ಸಾಮಾನ್ಯ ಆರೈಕೆ ಸಾರಾಂಶ ಕೇಳಿ","सामान्य देखभाल का सार सुनें"))
            }
            if(!s.careCatalogAvailable) {
                Notice(s.careText("Treatment information could not load","ಚಿಕಿತ್ಸೆ ಮಾಹಿತಿ ಲೋಡ್ ಆಗಲಿಲ್ಲ","उपचार की जानकारी लोड नहीं हुई"),s.careText("The packaged treatment library is unavailable. Try loading it again; do not assume that an empty screen means no action is needed.","ಸಂಗ್ರಹಿತ ಚಿಕಿತ್ಸೆಯ ಮಾಹಿತಿ ಲಭ್ಯವಿಲ್ಲ. ಮತ್ತೆ ಲೋಡ್ ಮಾಡಿ; ಖಾಲಿ ಪರದೆ ಕಂಡರೆ ಕ್ರಮ ಬೇಡವೆಂದು ಭಾವಿಸಬೇಡಿ.","पैक की गई उपचार पुस्तकालय उपलब्ध नहीं है। फिर से लोड करें; खाली स्क्रीन का अर्थ यह नहीं कि किसी कदम की जरूरत नहीं।"))
                Secondary(s.careText("Retry treatment library","ಚಿಕಿತ್ಸೆ ಮಾಹಿತಿ ಮತ್ತೆ ಲೋಡ್ ಮಾಡಿ","उपचार पुस्तकालय दोबारा लोड करें"),{a(AppAction.ReloadCareProtocols)})
            } else if(protocol!=null) {
                CareProtocolSections(s,protocol)
            } else {
                Notice(s.careText("Choose a condition to explore its care","ಆರೈಕೆ ತಿಳಿಯಲು ಸ್ಥಿತಿ ಆಯ್ಕೆಮಾಡಿ","देखभाल जानने के लिए स्थिति चुनें"),s.careText("This photo result cannot support disease-specific treatment. You can browse the complete library without changing that result.","ಈ ಚಿತ್ರ ಫಲಿತಾಂಶ ನಿರ್ದಿಷ್ಟ ರೋಗ ಚಿಕಿತ್ಸೆಗೆ ಬೆಂಬಲವಿಲ್ಲ. ಫಲಿತಾಂಶ ಬದಲಿಸದೆ ಸಂಪೂರ್ಣ ಮಾಹಿತಿ ನೋಡಬಹುದು.","इस तस्वीर के परिणाम से रोग विशेष का उपचार तय नहीं हो सकता। परिणाम बदले बिना पूरी पुस्तकालय देख सकते हैं।"))
                GuidanceCard(s.careText("Do now","ಈಗ ಮಾಡಿ","अभी करें"),listOf(s.careText("Take clear photos of the leaf, whole plant and nearby affected plants.","ಎಲೆ, ಇಡೀ ಗಿಡ ಮತ್ತು ಹತ್ತಿರದ ಪೀಡಿತ ಗಿಡಗಳ ಸ್ಪಷ್ಟ ಚಿತ್ರ ತೆಗೆಯಿರಿ.","पत्ती, पूरे पौधे और आसपास के प्रभावित पौधों की साफ तस्वीर लें।"),s.careText("Check soil moisture and avoid unnecessary sprays while the cause is uncertain.","ಮಣ್ಣಿನ ತೇವ ಪರಿಶೀಲಿಸಿ; ಕಾರಣ ಖಚಿತವಿಲ್ಲದಾಗ ಅನಗತ್ಯ ಸಿಂಪಡಣೆ ತಪ್ಪಿಸಿ.","मिट्टी की नमी जाँचें और कारण अनिश्चित होने पर अनावश्यक छिड़काव से बचें।")),CropColors.Green)
            }
            Secondary(s.careText("Browse all 17 conditions","ಎಲ್ಲಾ 17 ಸ್ಥಿತಿಗಳ ಮಾಹಿತಿ ನೋಡಿ","सभी 17 स्थितियाँ देखें"),{a(AppAction.OpenCareLibrary)})
            Text(s.careText("Conditional draft guidance. Product registration, crop label, harvest restrictions and local expert confirmation still apply. Recovery means protected new growth, not disappearance of old lesions.","ಇದು ಷರತ್ತಿನ ಪ್ರಾಯೋಗಿಕ ಸಲಹೆ. ಉತ್ಪನ್ನ ನೋಂದಣಿ, ಬೆಳೆ ಲೇಬಲ್, ಕೊಯ್ಲು ನಿಯಮ ಮತ್ತು ಸ್ಥಳೀಯ ತಜ್ಞರ ದೃಢೀಕರಣ ಅನ್ವಯಿಸುತ್ತದೆ. ಚೇತರಿಕೆ ಎಂದರೆ ಹೊಸ ಬೆಳವಣಿಗೆಯ ರಕ್ಷಣೆ; ಹಳೆಯ ಚುಕ್ಕೆ ಮಾಯವಾಗುವುದಲ್ಲ.","शर्तों पर आधारित प्रारूप मार्गदर्शन। उत्पाद का पंजीकरण, फसल का लेबल, कटाई संबंधी नियम और स्थानीय विशेषज्ञ की पुष्टि जरूरी है। सुधार का अर्थ नई बढ़त की रक्षा है, पुराने घावों का गायब होना नहीं।"),fontSize=11.sp,color=CropColors.Muted)
            ExpertCall(s)
        }
    }
}

@Composable private fun CareProtocolSections(s:AppUiState,protocol:com.debuggers.crophealth.content.CareProtocol) {
    val copy=protocol.copy
    Text(copy.goal,fontSize=15.sp,color=CropColors.Muted)
    if(s.advisory.healthyConflict) Notice(s.careText("Symptoms need a fresh check","ಲಕ್ಷಣಗಳನ್ನು ಮತ್ತೆ ಪರಿಶೀಲಿಸಬೇಕು","लक्षणों की फिर से जाँच जरूरी है"),s.careText("Do not rely on a healthy-looking photo when plants show damage, wilting or spread.","ಗಿಡದಲ್ಲಿ ಹಾನಿ, ಬಾಡುವಿಕೆ ಅಥವಾ ಹರಡುವಿಕೆ ಇದ್ದಾಗ ಆರೋಗ್ಯಕರ ಚಿತ್ರ ಅಂದಾಜು ನಂಬಬೇಡಿ.","जब पौधों में नुकसान, मुरझाना या फैलाव हो, तो स्वस्थ दिखने वाली तस्वीर पर निर्भर न रहें।"))
    val stage=CarePlanSelection.stage(copy.stagePlans,s.advisory.severity)
    if(stage!=null) {
        GuidanceCard(stage.title,stage.actions,if(s.advisory.severity==ReportedSeverity.SEVERE) CropColors.Rose else CropColors.Primary)
        AdvisoryAudio(s,"treatment_stage_"+s.advisory.severity.name.lowercase(Locale.ROOT),s.careText("Listen to action priorities","ಕ್ರಮದ ಆದ್ಯತೆಗಳನ್ನು ಕೇಳಿ","कदमों की प्राथमिकता सुनें"))
    } else if(s.advisory.severity==ReportedSeverity.UNKNOWN) {
        Text(s.careText("Damage level is unknown. The treatment information below is general; answer the questions to tailor action priorities.","ಹಾನಿಯ ಮಟ್ಟ ತಿಳಿದಿಲ್ಲ. ಕೆಳಗಿನ ಚಿಕಿತ್ಸೆ ಮಾಹಿತಿ ಸಾಮಾನ್ಯ; ಆದ್ಯತೆ ತಿಳಿಯಲು ಪ್ರಶ್ನೆಗಳಿಗೆ ಉತ್ತರಿಸಿ.","नुकसान का स्तर अज्ञात है। नीचे उपचार की सामान्य जानकारी है; प्राथमिकता तय करने के लिए प्रश्नों के उत्तर दें।"),fontSize=13.sp,color=CropColors.Muted)
        AdvisoryAudio(s,"treatment_stage_unknown",s.careText("Listen to next step","ಮುಂದಿನ ಕ್ರಮ ಕೇಳಿ","अगला कदम सुनें"))
    }
    AdvisoryAudio(s,"treatment_"+protocol.conditionId,s.careText("Listen to treatment & recovery summary","ಚಿಕಿತ್ಸೆ ಮತ್ತು ಚೇತರಿಕೆ ಸಾರಾಂಶ ಕೇಳಿ","उपचार और सुधार का सार सुनें"))
    GuidanceCard(s.careText("Check before treating","ಚಿಕಿತ್ಸೆಗೆ ಮೊದಲು ಪರಿಶೀಲಿಸಿ","उपचार से पहले जाँचें"),copy.confirmChecks,CropColors.Primary)
    GuidanceCard(s.careText("Similar-looking problems","ಹೋಲುವ ಲಕ್ಷಣಗಳ ಬೇರೆ ಕಾರಣಗಳು","ऐसे दिखने वाले दूसरे कारण"),copy.lookAlikes,CropColors.Gold)
    Text(s.careText("Treatment options","ಚಿಕಿತ್ಸೆಯ ಆಯ್ಕೆಗಳು","उपचार के विकल्प"),fontSize=23.sp,fontWeight=FontWeight.Medium)
    copy.treatmentOptions.forEach {option ->
        Surface(shape=RoundedCornerShape(18.dp),color=CropColors.Lavender,modifier=Modifier.fillMaxWidth().testTag("treatment_option_"+option.id)) {
            Column(Modifier.padding(16.dp),verticalArrangement=Arrangement.spacedBy(10.dp)) {
                Text(option.title,fontSize=18.sp,fontWeight=FontWeight.Medium)
                Text(option.whenToUse,fontSize=13.sp,color=CropColors.Primary)
                option.steps.forEachIndexed {index,line -> Text("${index+1}. $line",fontSize=14.sp,color=CropColors.Ink) }
                Text(option.limits,fontSize=12.sp,color=CropColors.Muted)
            }
        }
    }
    GuidanceCard(s.careText("Avoid these mistakes","ಈ ತಪ್ಪುಗಳನ್ನು ತಪ್ಪಿಸಿ","इन गलतियों से बचें"),copy.avoid,CropColors.Rose)
    GuidanceCard(s.careText("Signs management is helping","ನಿರ್ವಹಣೆ ಸಹಾಯವಾಗುತ್ತಿರುವ ಲಕ್ಷಣಗಳು","प्रबंधन से लाभ के संकेत"),copy.recoverySigns,CropColors.Green)
    GuidanceCard(s.careText("Signs to escalate","ಹೆಚ್ಚಿನ ನೆರವು ಬೇಕಾದ ಲಕ್ಷಣಗಳು","विशेषज्ञ की मदद लेने के संकेत"),copy.failureSigns,CropColors.Rose)
    Text(s.careText("Follow-up plan","ಮುಂದಿನ ಪರಿಶೀಲನೆ ಯೋಜನೆ","आगे की जाँच की योजना"),fontSize=23.sp,fontWeight=FontWeight.Medium)
    copy.followUp.forEach {checkpoint -> GuidanceCard(checkpoint.whenToCheck,listOf(checkpoint.check,checkpoint.action),CropColors.Primary) }
    GuidanceCard(s.careText("Ask your crop adviser","ಕೃಷಿ ಸಲಹೆಗಾರರನ್ನು ಕೇಳಿ","कृषि सलाहकार से पूछें"),copy.expertQuestions,CropColors.Gold)
    if(protocol.sources.isNotEmpty()) {
        Text(s.careText("References and review status","ಉಲ್ಲೇಖಗಳು ಮತ್ತು ಪರಿಶೀಲನೆ ಸ್ಥಿತಿ","संदर्भ और समीक्षा की स्थिति"),fontSize=15.sp,fontWeight=FontWeight.Medium)
        protocol.sources.forEach { Text(it.title+" · "+it.verificationStatus.replace('_',' '),fontSize=11.sp,color=CropColors.Muted) }
    }
    Text(protocol.version,fontSize=11.sp,color=CropColors.Muted)
}
@Composable private fun GuidanceCard(title:String,items:List<String>,accent:Color) {
    Surface(shape=RoundedCornerShape(18.dp),color=CropColors.Lavender,modifier=Modifier.fillMaxWidth()) {Row {
        Box(Modifier.width(4.dp).heightIn(min=112.dp).background(accent));Column(Modifier.padding(16.dp),verticalArrangement=Arrangement.spacedBy(8.dp)) {Text(title,fontSize=16.sp,fontWeight=FontWeight.Medium);items.forEach {Text("• $it",fontSize=13.sp,color=CropColors.Muted)}}
    }}}

@Composable private fun ConcernScreen(s:AppUiState,a:(AppAction)->Unit,prompt:(String)->Prompt) {
    var question by rememberSaveable {mutableIntStateOf(0)}
    var draftAnswers by rememberSaveable {mutableStateOf(ArrayList(CareAnswerDraft.seed(s.careSymptoms,s.careSymptomsComplete)))}
    var selected by rememberSaveable {mutableIntStateOf(draftAnswers[0])}
    val questions=listOf(
        s.careText("Are the symptoms spreading quickly?","ಲಕ್ಷಣಗಳು ಬೇಗ ಹರಡುತ್ತಿವೆಯೇ?","क्या लक्षण तेजी से फैल रहे हैं?"),
        s.careText("How much of this leaf looks affected?","ಈ ಎಲೆಯ ಎಷ್ಟು ಭಾಗ ಪೀಡಿತವಾಗಿದೆ?","इस पत्ते का कितना हिस्सा प्रभावित है?"),
        s.careText("Are many plants affected?","ಅನೇಕ ಸಸ್ಯಗಳು ಪೀಡಿತವಾಗಿವೆಯೇ?","क्या कई पौधे प्रभावित हैं?"),
        s.careText("Are plants wilting or dying?","ಗಿಡಗಳು ಬಾಡುತ್ತಿವೆಯೇ ಅಥವಾ ಸಾಯುತ್ತಿವೆಯೇ?","क्या पौधे मुरझा रहे हैं या मर रहे हैं?"),
        s.careText("Are fruit, tubers or stems affected?","ಹಣ್ಣು, ಗೆಡ್ಡೆ ಅಥವಾ ಕಾಂಡಕ್ಕೆ ಹಾನಿಯಿದೆಯೇ?","क्या फल, कंद या तने प्रभावित हैं?"),
        s.careText("Has the crop been in wet or humid conditions?","ಬೆಳೆ ತೇವ ಅಥವಾ ಆರ್ದ್ರ ಪರಿಸ್ಥಿತಿಯಲ್ಲಿದೆಯೇ?","क्या फसल के आसपास नमी या आर्द्रता रही है?"),
    )
    if(question>=6) Page {
        Text(s.careText("Your care assessment","ನಿಮ್ಮ ಆರೈಕೆ ಪರಿಶೀಲನೆ","आपका देखभाल आकलन"),fontSize=28.sp,fontWeight=FontWeight.Medium)
        AdvisorySummary(s)
        ExpertCall(s)
        Primary(s.careText("See the care plan","ಆರೈಕೆ ಯೋಜನೆ ನೋಡಿ","देखभाल योजना देखें"),{a(AppAction.Navigate(Screen.GUIDANCE))})
        Secondary(s.careText(if(s.manualCare!=null) "Back to care library" else "Return to result",if(s.manualCare!=null) "ಆರೈಕೆ ಮಾಹಿತಿಗೆ ಹಿಂತಿರುಗಿ" else "ಫಲಿತಾಂಶಕ್ಕೆ ಹಿಂತಿರುಗಿ",if(s.manualCare!=null) "देखभाल पुस्तकालय पर लौटें" else "परिणाम पर लौटें"),{a(AppAction.Navigate(if(s.manualCare!=null) Screen.CARE_LIBRARY else Screen.RESULT))})
    } else Page {
        Text(s.careText("Question ${question+1} of 6","ಪ್ರಶ್ನೆ ${question+1} / 6","प्रश्न ${question+1} / 6"),fontSize=12.sp,color=CropColors.Muted)
        LinearProgressIndicator(progress={(question+1)/6f},modifier=Modifier.fillMaxWidth().height(5.dp).clip(CircleShape),color=CropColors.Primary,trackColor=CropColors.Border)
        Text(questions[question],fontSize=25.sp,fontWeight=FontWeight.Medium)
        if(question==1) AdvisoryAudio(s,"advisory_question_coverage",s.careText("Read question aloud","ಪ್ರಶ್ನೆಯನ್ನು ಕೇಳಿ","प्रश्न सुनें"))
        else if(question<3) AudioButton(prompt(listOf("concern_spreading","concern_coverage","concern_plants")[question]).audioAsset,s.tr("Read question aloud","ಪ್ರಶ್ನೆಯನ್ನು ಕೇಳಿ"))
        else AdvisoryAudio(s,"advisory_question_"+listOf("wilting","fruit_stem","wet_weather")[question-3],s.careText("Read question aloud","ಪ್ರಶ್ನೆಯನ್ನು ಕೇಳಿ","प्रश्न सुनें"))
        val options=if(question==1) listOf(
            s.careText("No visible damage · 0%","ಕಾಣುವ ಹಾನಿ ಇಲ್ಲ · 0%","कोई दिखने वाला नुकसान नहीं · 0%"),
            s.careText("A few spots · less than 10%","ಕೆಲವು ಚುಕ್ಕೆಗಳು · 10% ಕ್ಕಿಂತ ಕಡಿಮೆ","कुछ धब्बे · 10% से कम"),
            s.careText("Some damage · about 10–30%","ಸ್ವಲ್ಪ ಹಾನಿ · ಸುಮಾರು 10–30%","कुछ नुकसान · लगभग 10–30%"),
            s.careText("Many spots · more than 30%","ಹಲವು ಚುಕ್ಕೆಗಳು · 30% ಕ್ಕಿಂತ ಹೆಚ್ಚು","बहुत धब्बे · 30% से अधिक"),
            s.careText("I'm not sure","ಖಚಿತವಿಲ್ಲ","मुझे पक्का नहीं"))
        else listOf(s.careText("Yes","ಹೌದು","हाँ"),s.careText("No","ಇಲ್ಲ","नहीं"),s.careText("I'm not sure","ಖಚಿತವಿಲ್ಲ","मुझे पक्का नहीं"))
        options.forEachIndexed {index,label ->
            Surface(onClick={selected=index},shape=RoundedCornerShape(18.dp),color=if(selected==index) CropColors.Lavender else Color.White,
                border=BorderStroke(if(selected==index) 1.5.dp else 1.dp,if(selected==index) CropColors.Primary else CropColors.Border),modifier=Modifier.fillMaxWidth().testTag("care_answer_$index")) {
                Row(Modifier.padding(horizontal=16.dp,vertical=10.dp),verticalAlignment=Alignment.CenterVertically) {
                    RadioButton(selected=selected==index,onClick={selected=index});Spacer(Modifier.width(12.dp));Text(label,fontSize=16.sp)
                }
            }
        }
        Primary(s.careText(if(question==5 && s.manualCare!=null) "See treatment & recovery plan" else if(question==5) "See assessment" else "Next",if(question==5 && s.manualCare!=null) "ಚಿಕಿತ್ಸೆ ಮತ್ತು ಚೇತರಿಕೆ ಯೋಜನೆ ನೋಡಿ" else if(question==5) "ಪರಿಶೀಲನೆ ನೋಡಿ" else "ಮುಂದೆ",if(question==5 && s.manualCare!=null) "उपचार और सुधार योजना देखें" else if(question==5) "आकलन देखें" else "आगे"),{
            val updated=ArrayList(draftAnswers).also {it[question]=selected}
            draftAnswers=updated
            a(AppAction.ReportSymptoms(CareAnswerDraft.symptoms(updated),completed=question==5))
            val opensManualPlan=question==5 && s.manualCare!=null
            question++
            selected=if(question<6) updated[question] else -1
            if(opensManualPlan) a(AppAction.Navigate(Screen.GUIDANCE))
        },Icons.Outlined.ArrowForward,enabled=selected>=0)
        Text(s.careText("Report what you see. These answers do not confirm a disease.","ನೀವು ಗಮನಿಸಿದುದನ್ನು ತಿಳಿಸಿ. ಈ ಉತ್ತರ ರೋಗ ದೃಢಪಡಿಸುವುದಿಲ್ಲ.","जो दिख रहा है वह बताएँ। ये उत्तर किसी रोग की पुष्टि नहीं करते।"),fontSize=12.sp,color=CropColors.Muted)
    }
}

@Composable private fun HistoryScreen(s:AppUiState,a:(AppAction)->Unit) {
    var crop by remember {mutableStateOf<Crop?>(null)}
    val records=s.observations.filter {crop==null || it.crop==crop}
    Column(Modifier.fillMaxSize().padding(horizontal=20.dp),verticalArrangement=Arrangement.spacedBy(16.dp)) {
        Spacer(Modifier.height(10.dp))
        Text(s.tr("History","ಇತಿಹಾಸ"),fontSize=30.sp,fontWeight=FontWeight.Medium)
        Text(s.tr("Saved on this phone. Available offline.","ಈ ಫೋನ್‌ನಲ್ಲಿ ಉಳಿಸಲಾಗಿದೆ. ಆಫ್‌ಲೈನ್‌ನಲ್ಲಿ ಲಭ್ಯ."),fontSize=12.sp,color=CropColors.Green)
        CropChips(s,a,true,crop) {crop=it}
        if(records.isEmpty()) SoftCard {
            Icon(Icons.Outlined.History,null,tint=CropColors.Primary)
            Text(s.tr("No scans here yet","ಇನ್ನೂ ಪರಿಶೀಲನೆಗಳಿಲ್ಲ"),fontSize=19.sp)
            Text(s.tr("Save an observation after checking a leaf.","ಎಲೆ ಪರಿಶೀಲಿಸಿದ ನಂತರ ವೀಕ್ಷಣೆಯನ್ನು ಉಳಿಸಿ."),fontSize=13.sp,color=CropColors.Muted)
        } else LazyColumn(Modifier.fillMaxWidth().testTag("history_list"),contentPadding=PaddingValues(bottom=24.dp),verticalArrangement=Arrangement.spacedBy(12.dp)) {
            records.groupBy {dateGroup(it.createdAt,s)}.forEach {(group,items) ->
                item(key="date_$group") {Section(group)}
                items(items,key={it.id}) {HistoryCard(it,s,a)}
            }
        }
    }
}
private fun dateGroup(time:Long,s:AppUiState):String {
    val format=SimpleDateFormat("yyyyMMdd",Locale.ROOT);val today=format.format(Date());val day=format.format(Date(time));val yesterday=format.format(Date(System.currentTimeMillis()-86400000))
    return when(day) {today->s.tr("Today","ಇಂದು");yesterday->s.tr("Yesterday","ನಿನ್ನೆ");else->s.tr("Earlier","ಹಿಂದಿನ")}
}
private fun Observation.isAcceptedModelMatch():Boolean = resultType=="likely_condition" || resultType=="healthy_looking"
private fun Observation.isPrototypePrediction(s:AppUiState):Boolean = resultType in setOf("uncertain","crop_mismatch") && conditionId!=null &&
    !hidesUnsupportedCandidate() &&
    (isLeafCheckedCandidate() || note.startsWith("Prototype prediction:") || (s.model.sourceEvaluated && modelVersion==s.model.version))
private fun AppUiState.predictionText(en:String,kn:String,hi:String):String = when(language) {
    AppLanguage.ENGLISH -> en
    AppLanguage.KANNADA -> kn
    AppLanguage.HINDI -> hi
}

@Composable private fun HistoryCard(o:Observation,s:AppUiState,a:(AppAction)->Unit) {
    val accepted=o.isAcceptedModelMatch()
    val prediction=o.isPrototypePrediction(s)
    Surface(shape=RoundedCornerShape(18.dp),color=CropColors.Lavender,modifier=Modifier.fillMaxWidth().clickable {a(AppAction.OpenObservation(o.id))}) {
        Row(Modifier.padding(12.dp),verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(12.dp)) {
            Photo(o.imagePath,Modifier.size(60.dp),160);Column(Modifier.weight(1f),verticalArrangement=Arrangement.spacedBy(4.dp)) {
                Text(if(accepted || prediction) Conditions.byId(o.conditionId.orEmpty())?.displayName(s.language) ?: s.tr("Leaf observation","ಎಲೆಯ ವೀಕ್ಷಣೆ") else s.tr("Needs review","ಪರಿಶೀಲನೆ ಅಗತ್ಯ"),fontSize=15.sp,fontWeight=FontWeight.Medium)
                Text(o.crop.displayName(s.language)+" · "+SimpleDateFormat("h:mm a",Locale.getDefault()).format(Date(o.createdAt)),fontSize=11.sp,color=CropColors.Muted)
                Text(when {accepted && o.validated->s.tr("Model assessment","ಮಾದರಿಯ ಪರಿಶೀಲನೆ");accepted->s.tr("Model match","ಮಾದರಿಯ ಹೊಂದಾಣಿಕೆ");prediction && o.resultType=="crop_mismatch"->s.predictionText("Prediction · Crop mismatch","ಊಹೆ · ಬೆಳೆ ಹೊಂದಿಕೆಯಾಗುತ್ತಿಲ್ಲ","अनुमान · फसल का मेल नहीं");prediction->s.predictionText("Prediction · Low confidence","ಊಹೆ · ಕಡಿಮೆ ವಿಶ್ವಾಸ","अनुमान · कम भरोसा");else->s.tr("Uncertain observation","ಅನಿಶ್ಚಿತ ವೀಕ್ಷಣೆ")},fontSize=10.sp,color=CropColors.Gold)
            }
            IconButton(onClick={a(AppAction.DeleteObservation(o.id))}) {Icon(Icons.Outlined.DeleteOutline,s.tr("Delete scan","ಪರಿಶೀಲನೆ ಅಳಿಸಿ"),tint=CropColors.Muted,modifier=Modifier.size(19.dp))}
        }
    }
}

@Composable private fun HelpScreen(s:AppUiState,a:(AppAction)->Unit,prompt:(String)->Prompt) {
    Page {
        Spacer(Modifier.height(10.dp));Text(s.tr("Here to help","ಸಹಾಯಕ್ಕಾಗಿ ಇಲ್ಲಿದ್ದೇವೆ"),fontSize=30.sp,fontWeight=FontWeight.Medium)
        Text(s.tr("A better photo makes a better starting point.","ಉತ್ತಮ ಫೋಟೋ ಉತ್ತಮ ಆರಂಭಕ್ಕೆ ಸಹಾಯ ಮಾಡುತ್ತದೆ."),fontSize=13.sp,color=CropColors.Muted)
        listOf(s.tr("Find natural light","ನೈಸರ್ಗಿಕ ಬೆಳಕು ಹುಡುಕಿ") to s.tr("Avoid deep shadows and bright glare.","ಗಾಢ ನೆರಳು ಮತ್ತು ಪ್ರಖರ ಹೊಳಪು ತಪ್ಪಿಸಿ."),s.tr("Hold one leaf steady","ಒಂದು ಎಲೆಯನ್ನು ಸ್ಥಿರವಾಗಿ ಹಿಡಿಯಿರಿ") to s.tr("Keep the leaf sharp and inside the frame.","ಎಲೆ ಸ್ಪಷ್ಟವಾಗಿ ಚೌಕಟ್ಟಿನೊಳಗೆ ಇರಲಿ."),s.tr("Get close, keep it simple","ಹತ್ತಿರ ಹೋಗಿ, ಸರಳವಾಗಿರಿಸಿ") to s.tr("Avoid several leaves overlapping.","ಹಲವು ಎಲೆಗಳು ಒಂದರ ಮೇಲೊಂದು ಬರುವುದನ್ನು ತಪ್ಪಿಸಿ.")).forEachIndexed {i,(title,body) ->
            SoftCard {Row(horizontalArrangement=Arrangement.spacedBy(12.dp)) {Box(Modifier.size(28.dp).background(CropColors.Primary,CircleShape),contentAlignment=Alignment.Center) {Text("${i+1}",color=Color.White,fontSize=12.sp)};Column {Text(title,fontSize=16.sp);Spacer(Modifier.height(5.dp));Text(body,fontSize=12.sp,color=CropColors.Muted)}}}
        }
        SoftCard {Text(s.tr("What does the score mean?","ಅಂಕದ ಅರ್ಥವೇನು?"),fontSize=16.sp);Text(s.tr("A model score describes a candidate match. It is not a guarantee or a treatment instruction. Unvalidated scores need expert review.","ಮಾದರಿಯ ಅಂಕ ಒಂದು ಸಾಧ್ಯತೆಯ ಹೊಂದಾಣಿಕೆಯನ್ನು ಸೂಚಿಸುತ್ತದೆ. ಇದು ಖಾತರಿ ಅಥವಾ ಚಿಕಿತ್ಸೆಯ ಸೂಚನೆಯಲ್ಲ. ದೃಢೀಕರಿಸದ ಅಂಕಗಳಿಗೆ ತಜ್ಞರ ಪರಿಶೀಲನೆ ಅಗತ್ಯ."),fontSize=13.sp,color=CropColors.Muted)}
        Column(verticalArrangement=Arrangement.spacedBy(10.dp)) {Text(s.tr("Language & voice","ಭಾಷೆ ಮತ್ತು ಧ್ವನಿ"),fontSize=16.sp);LanguageToggle(s,a)}
        AudioButton(prompt("uncertain").audioAsset,s.tr("Try offline voice","ಆಫ್‌ಲೈನ್ ಧ್ವನಿ ಕೇಳಿ"))
        SoftCard {Row(verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(8.dp)) {Icon(if(s.model.ready) Icons.Outlined.CheckCircle else Icons.Outlined.Info,null,tint=if(s.model.ready) CropColors.Green else CropColors.Gold);Text(if(s.model.ready) s.tr("Local model installed","ಸ್ಥಳೀಯ ಮಾದರಿ ಸ್ಥಾಪಿಸಲಾಗಿದೆ") else s.tr("Local model unavailable","ಸ್ಥಳೀಯ ಮಾದರಿ ಲಭ್ಯವಿಲ್ಲ"),fontSize=15.sp)};Text(s.tr(s.model.message,s.model.message),fontSize=12.sp,color=CropColors.Muted);Text(s.model.name+" · "+s.model.version,fontSize=10.sp,color=CropColors.Muted)}
        Secondary(s.tr("Model, privacy & settings","ಮಾದರಿ, ಗೌಪ್ಯತೆ ಮತ್ತು ಸೆಟ್ಟಿಂಗ್‌ಗಳು"),{a(AppAction.Navigate(Screen.SETTINGS))},Icons.Outlined.Settings)
        ExpertCall(s)
    }
}

@Composable private fun SettingsScreen(s:AppUiState,a:(AppAction)->Unit) {
    var clear by remember {mutableStateOf(false)}
    Page {
        Text(s.tr("On this phone","ಈ ಫೋನ್‌ನಲ್ಲಿ"),fontSize=28.sp,fontWeight=FontWeight.Medium)
        LanguageToggle(s,a)
        Row(Modifier.fillMaxWidth(),verticalAlignment=Alignment.CenterVertically) {Column(Modifier.weight(1f)) {Text(s.tr("Play guidance automatically","ಮಾರ್ಗದರ್ಶನ ಸ್ವಯಂಚಾಲಿತವಾಗಿ ಕೇಳಿ"),fontSize=15.sp);Text(s.tr("Uses bundled audio, no internet.","ಸಂಗ್ರಹಿತ ಧ್ವನಿ ಬಳಸುತ್ತದೆ, ಇಂಟರ್ನೆಟ್ ಬೇಡ."),fontSize=11.sp,color=CropColors.Muted)};Switch(checked=s.autoAudio,onCheckedChange={a(AppAction.SetAutoAudio(it))})}
        SoftCard {Text(s.model.name,fontSize=17.sp);Text(s.tr(s.model.message,s.model.message),fontSize=13.sp,color=CropColors.Muted);Text(s.tr("Version: ${s.model.version}","ಆವೃತ್ತಿ: ${s.model.version}"),fontSize=11.sp,color=CropColors.Muted);if(s.model.bytes>0) Text("${"%.1f".format(s.model.bytes/1048576.0)} MB · "+s.tr("bundled locally","ಸ್ಥಳೀಯವಾಗಿ ಸಂಗ್ರಹಿಸಲಾಗಿದೆ"),fontSize=11.sp,color=CropColors.Muted)}
        SoftCard {Text(s.tr("Your photos stay here","ನಿಮ್ಮ ಫೋಟೋಗಳು ಇಲ್ಲಿಯೇ ಉಳಿಯುತ್ತವೆ"),fontSize=17.sp);Text(s.tr("Assessment runs locally. Photos leave the app only when you choose to share an observation.","ಪರಿಶೀಲನೆ ಸ್ಥಳೀಯವಾಗಿ ನಡೆಯುತ್ತದೆ. ನೀವು ಹಂಚಿಕೊಳ್ಳಲು ಆಯ್ಕೆ ಮಾಡಿದಾಗ ಮಾತ್ರ ಫೋಟೋ ಹೊರಗೆ ಹೋಗುತ್ತದೆ."),fontSize=13.sp,color=CropColors.Muted)}
        SoftCard {Text(s.tr("Prototype content","ಪ್ರಾಯೋಗಿಕ ವಿಷಯ"),fontSize=16.sp);Text(s.tr("Model validation, agricultural review and Kannada and Hindi translation review are still pending. Guidance is for observation, not a chemical prescription.","ಮಾದರಿಯ ದೃಢೀಕರಣ, ಕೃಷಿ ಪರಿಶೀಲನೆ ಹಾಗೂ ಕನ್ನಡ ಮತ್ತು ಹಿಂದಿ ಅನುವಾದ ಪರಿಶೀಲನೆ ಬಾಕಿಯಿವೆ. ಮಾರ್ಗದರ್ಶನ ವೀಕ್ಷಣೆಗಾಗಿ, ರಾಸಾಯನಿಕ ಚಿಕಿತ್ಸೆಯ ಸೂಚನೆಯಲ್ಲ."),fontSize=12.sp,color=CropColors.Muted)}
        TextButton(onClick={clear=true}) {Icon(Icons.Outlined.DeleteOutline,null);Spacer(Modifier.width(8.dp));Text(s.tr("Clear saved history","ಉಳಿಸಿದ ಇತಿಹಾಸ ಅಳಿಸಿ"))}
        Text("Debuggers · Build Beyond ’26",fontSize=11.sp,color=CropColors.Muted)
    }
    if(clear) AlertDialog(onDismissRequest={clear=false},title={Text(s.tr("Delete saved observations?","ಉಳಿಸಿದ ವೀಕ್ಷಣೆಗಳನ್ನು ಅಳಿಸಬೇಕೇ?"))},text={Text(s.tr("Their saved images will also be removed from this app.","ಈ ಅಪ್ಲಿಕೇಶನ್‌ನಲ್ಲಿರುವ ಅವುಗಳ ಚಿತ್ರಗಳೂ ಅಳಿಯುತ್ತವೆ."))},confirmButton={TextButton(onClick={a(AppAction.ClearHistory);clear=false}) {Text(s.tr("Delete","ಅಳಿಸಿ"))}},dismissButton={TextButton(onClick={clear=false}) {Text(s.tr("Cancel","ರದ್ದುಮಾಡಿ"))}})
}

@Composable private fun ExpertCall(s:AppUiState) {
    val context=LocalContext.current;var show by remember {mutableStateOf(false)};var number by remember {mutableStateOf("")}
    Button(onClick={show=true},colors=ButtonDefaults.buttonColors(containerColor=CropColors.Gold,contentColor=Color.White),shape=RoundedCornerShape(15.dp),modifier=Modifier.fillMaxWidth().heightIn(min=48.dp)) {Icon(Icons.Outlined.Call,null,Modifier.size(18.dp));Spacer(Modifier.width(9.dp));Text(s.tr("Call a local crop expert","ಸ್ಥಳೀಯ ಕೃಷಿ ತಜ್ಞರಿಗೆ ಕರೆ ಮಾಡಿ"),fontSize=14.sp)}
    if(show) AlertDialog(onDismissRequest={show=false},title={Text(s.tr("Choose your expert contact","ನಿಮ್ಮ ತಜ್ಞರ ಸಂಪರ್ಕ ಆಯ್ಕೆಮಾಡಿ"))},text={Column(verticalArrangement=Arrangement.spacedBy(10.dp)) {Text(s.tr("Enter a number you trust. This app does not verify hotline availability. Calling needs phone service.","ನೀವು ನಂಬುವ ಸಂಖ್ಯೆಯನ್ನು ನಮೂದಿಸಿ. ಕರೆ ಮಾಡಲು ದೂರವಾಣಿ ಸೇವೆ ಬೇಕು."),fontSize=13.sp);OutlinedTextField(value=number,onValueChange={number=it.filter {c->c.isDigit() || c=='+'}},label={Text(s.tr("Phone number","ದೂರವಾಣಿ ಸಂಖ್ಯೆ"))},singleLine=true)}},confirmButton={TextButton(enabled=number.length>=5,onClick={runCatching {context.startActivity(Intent(Intent.ACTION_DIAL,Uri.parse("tel:$number")))};show=false}) {Text(s.tr("Open dialer","ಡಯಲರ್ ತೆರೆಯಿರಿ"))}},dismissButton={TextButton(onClick={show=false}) {Text(s.tr("Cancel","ರದ್ದುಮಾಡಿ"))}})
}

/** Only one bundled narration may play, including multiple care cards on a page. */
private object NarrationPlayback {
    private var owner: Any? = null
    private var stopCurrent: (() -> Unit)? = null
    fun claim(next: Any, stop: () -> Unit) {
        if(owner !== next) stopCurrent?.invoke()
        owner=next;stopCurrent=stop
    }
    fun release(current: Any) {if(owner===current) {owner=null;stopCurrent=null}}
}

@Composable fun AudioButton(asset:String?,label:String,autoPlay:Boolean=false) {
    val context=LocalContext.current;var player by remember {mutableStateOf<MediaPlayer?>(null)};var playing by remember {mutableStateOf(false)};var failed by remember {mutableStateOf(false)}
    val narrationOwner=remember {Any()}
    val unavailable=when(LocalAppLanguage.current) {AppLanguage.ENGLISH -> "Audio unavailable";AppLanguage.KANNADA -> "ಧ್ವನಿ ಲಭ್ಯವಿಲ್ಲ";AppLanguage.HINDI -> HindiUi.translate("Audio unavailable")}
    fun stop() { player?.let { current -> runCatching { current.stop() }; current.release() }; player=null;playing=false;NarrationPlayback.release(narrationOwner) }
    fun play() {
        if(asset==null) return
        stop();failed=false;NarrationPlayback.claim(narrationOwner) {stop()}
        runCatching {
            val afd=context.assets.openFd(asset);val next=MediaPlayer();next.setDataSource(afd.fileDescriptor,afd.startOffset,afd.length);afd.close();player=next
            next.setOnCompletionListener {stop()}
            next.setOnErrorListener {_,_,_->failed=true;stop();true}
            next.prepare();next.start();playing=true
        }.onFailure {failed=true;stop()}
    }
    DisposableEffect(asset) {onDispose {stop()}}
    LaunchedEffect(asset,autoPlay) {if(autoPlay && asset!=null) play()}
    OutlinedButton(onClick={if(playing) stop() else play()},enabled=asset!=null,shape=RoundedCornerShape(15.dp),border=BorderStroke(1.dp,CropColors.Border),modifier=Modifier.fillMaxWidth().heightIn(min=47.dp)) {Icon(if(playing) Icons.Outlined.StopCircle else Icons.Outlined.VolumeUp,null,Modifier.size(19.dp));Spacer(Modifier.width(9.dp));Text(if(failed) unavailable else label,fontSize=14.sp)}
}

@Composable private fun Photo(path:String?,modifier:Modifier,maxSide:Int=900) {
    val description=when(LocalAppLanguage.current) {AppLanguage.ENGLISH -> "Leaf photo";AppLanguage.KANNADA -> "ಎಲೆಯ ಫೋಟೋ";AppLanguage.HINDI -> HindiUi.translate("Leaf photo")}
    val decodeLimit=maxSide.coerceIn(32,1024)
    // The producer is cancelled when its file/bounds change or this image leaves composition.
    // Bitmap ownership stays with Compose/GC: never recycle an image it may still draw.
    val image by produceState<androidx.compose.ui.graphics.ImageBitmap?>(null,path,decodeLimit) {
        value=null
        if(path.isNullOrBlank()) return@produceState
        val decoded=kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) {
            currentCoroutineContext().ensureActive()
            runCatching {ImagePreparation.decode(File(path),decodeLimit).bitmap.asImageBitmap()}.getOrNull()
        }
        currentCoroutineContext().ensureActive()
        value=decoded
    }
    Box(modifier.clip(RoundedCornerShape(16.dp)).background(CropColors.Lavender),contentAlignment=Alignment.Center) {
        if(image!=null) Image(image!!,description,Modifier.fillMaxSize(),contentScale=ContentScale.Crop)
        else Icon(Icons.Outlined.Grass,description,tint=CropColors.Primary,modifier=Modifier.size(32.dp))
    }
}
@Composable private fun Section(title:String) {Text(title,fontSize=18.sp,fontWeight=FontWeight.Medium)}
@Composable private fun SoftCard(content:@Composable ColumnScope.()->Unit) {Surface(shape=RoundedCornerShape(18.dp),color=CropColors.Lavender,modifier=Modifier.fillMaxWidth()) {Column(Modifier.padding(16.dp),verticalArrangement=Arrangement.spacedBy(10.dp),content=content)}}
@Composable private fun MiniCard(title:String,body:String,modifier:Modifier=Modifier) {Surface(shape=RoundedCornerShape(16.dp),color=CropColors.Lavender,modifier=modifier) {Column(Modifier.padding(14.dp),verticalArrangement=Arrangement.spacedBy(6.dp)) {Text(title,fontSize=13.sp,fontWeight=FontWeight.Medium);Text(body,fontSize=10.sp,color=CropColors.Muted)}}}
@Composable private fun Notice(title:String,body:String) {Surface(shape=RoundedCornerShape(18.dp),color=CropColors.PaleGold,modifier=Modifier.fillMaxWidth()) {Column(Modifier.padding(17.dp),verticalArrangement=Arrangement.spacedBy(7.dp)) {Row(horizontalArrangement=Arrangement.spacedBy(8.dp),verticalAlignment=Alignment.CenterVertically) {Icon(Icons.Outlined.Info,null,tint=CropColors.Gold,modifier=Modifier.size(19.dp));Text(title,fontSize=18.sp,fontWeight=FontWeight.Medium)};Text(body,fontSize=13.sp,color=CropColors.Muted)}}}
@Composable private fun Primary(label:String,click:()->Unit,icon:ImageVector?=null,modifier:Modifier=Modifier,enabled:Boolean=true) {Button(onClick=click,enabled=enabled,shape=RoundedCornerShape(15.dp),modifier=modifier.fillMaxWidth().heightIn(min=50.dp)) {if(icon!=null) {Icon(icon,null,Modifier.size(19.dp));Spacer(Modifier.width(9.dp))};Text(label,fontSize=14.sp)}}
@Composable private fun Secondary(label:String,click:()->Unit,icon:ImageVector?=null,enabled:Boolean=true) {OutlinedButton(onClick=click,enabled=enabled,shape=RoundedCornerShape(15.dp),border=BorderStroke(1.dp,CropColors.Border),modifier=Modifier.fillMaxWidth().heightIn(min=48.dp)) {if(icon!=null) {Icon(icon,null,Modifier.size(18.dp));Spacer(Modifier.width(8.dp))};Text(label,fontSize=14.sp)}}
