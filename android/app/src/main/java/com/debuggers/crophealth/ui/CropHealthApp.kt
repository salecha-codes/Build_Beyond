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
        val mainTabs=state.screen in listOf(Screen.HOME,Screen.HISTORY,Screen.HELP)
        BackHandler(enabled=state.screen!=Screen.HOME) { onAction(AppAction.Navigate(when(state.screen) { Screen.GUIDANCE,Screen.CONCERN -> Screen.RESULT; Screen.SETTINGS -> Screen.HELP; Screen.RESULT -> if(state.openedObservation!=null) Screen.HISTORY else Screen.HOME; else -> Screen.HOME })) }
        if(state.screen==Screen.CAPTURE) {
            CameraScreen(state,onAction,newCameraFile)
        } else Scaffold(
            containerColor=Color.White,
            topBar={if(!mainTabs && state.screen!=Screen.WELCOME) Header(state,onAction)},
            bottomBar={if(mainTabs) BottomTabs(state,onAction)},
        ) { padding ->
            Box(Modifier.fillMaxSize().padding(padding)) {
                when(state.screen) {
                    Screen.WELCOME -> Welcome(state,onAction)
                    Screen.HOME -> Home(state,onAction)
                    Screen.PHOTO_REVIEW -> PhotoReview(state,onAction)
                    Screen.PROCESSING -> Processing(state)
                    Screen.RESULT -> Result(state,onAction,prompt)
                    Screen.GUIDANCE -> GuidanceScreen(state,onAction,prompt)
                    Screen.CONCERN -> ConcernScreen(state,onAction,prompt)
                    Screen.HISTORY -> HistoryScreen(state,onAction)
                    Screen.HELP -> HelpScreen(state,onAction,prompt)
                    Screen.SETTINGS -> SettingsScreen(state,onAction)
                    Screen.CAPTURE -> Unit
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
    TopAppBar(title={},navigationIcon={IconButton(onClick={a(AppAction.Navigate(when(s.screen) { Screen.GUIDANCE,Screen.CONCERN -> Screen.RESULT; Screen.SETTINGS -> Screen.HELP; Screen.RESULT -> if(s.openedObservation!=null) Screen.HISTORY else Screen.HOME; else -> Screen.HOME }))}) {Icon(Icons.Outlined.ArrowBack,s.tr("Back","ಹಿಂದೆ"))}},
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
        Spacer(Modifier.height(28.dp));Text(s.tr("Crop Health","ಬೆಳೆ ಆರೋಗ್ಯ"),fontSize=32.sp,fontWeight=FontWeight.Medium)
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
    val certain=result is AssessmentResult.LikelyCondition || result is AssessmentResult.HealthyLooking || stored?.validated==true
    val top=evidence?.ranked?.firstOrNull()
    val condition=top?.condition ?: stored?.conditionId?.let(Conditions::byId)
    val isRetake=result is AssessmentResult.Retake
    val unavailable=result is AssessmentResult.ModelUnavailable
    val cropMismatch=result is AssessmentResult.CropMismatch
    val title=when {
        isRetake ->s.tr("Let's take another photo","ಇನ್ನೊಂದು ಫೋಟೋ ತೆಗೆಯೋಣ")
        unavailable ->s.tr("Assessment unavailable","ಪರಿಶೀಲನೆ ಲಭ್ಯವಿಲ್ಲ")
        cropMismatch ->s.tr("Check the selected crop","ಆಯ್ಕೆ ಮಾಡಿದ ಬೆಳೆ ಪರಿಶೀಲಿಸಿ")
        certain ->condition?.displayName(s.language) ?: s.tr("Leaf assessment","ಎಲೆಯ ಪರಿಶೀಲನೆ")
        else ->s.tr("Not sure about this one","ಈ ಫೋಟೋದ ಬಗ್ಗೆ ಖಚಿತವಿಲ್ಲ")
    }
    Page {
        if(!certain) Notice(title,when {
            isRetake ->s.tr("Try a brighter, sharper close-up of one leaf.","ಒಂದು ಎಲೆಯ ಹೆಚ್ಚು ಬೆಳಕಿನ ಸ್ಪಷ್ಟ ಫೋಟೋ ತೆಗೆಯಿರಿ.")
            unavailable ->s.tr("No diagnosis was produced. Your photo stays on this phone.","ಯಾವುದೇ ರೋಗನಿರ್ಣಯ ಮಾಡಲಾಗಿಲ್ಲ. ಫೋಟೋ ಈ ಫೋನ್‌ನಲ್ಲೇ ಉಳಿಯುತ್ತದೆ.")
            cropMismatch ->s.tr("The model candidate and selected crop differ. Please check and retake.","ಮಾದರಿಯ ಊಹೆ ಮತ್ತು ಆಯ್ಕೆ ಮಾಡಿದ ಬೆಳೆ ಬೇರೆ ಇವೆ. ಪರಿಶೀಲಿಸಿ ಮತ್ತೆ ಫೋಟೋ ತೆಗೆಯಿರಿ.")
            else ->s.tr("These are possible matches, not a confirmed diagnosis. Ask a local crop expert when needed.","ಇವು ಸಾಧ್ಯತೆಗಳು ಮಾತ್ರ, ದೃಢಪಟ್ಟ ರೋಗನಿರ್ಣಯವಲ್ಲ. ಅಗತ್ಯವಿದ್ದರೆ ಸ್ಥಳೀಯ ಕೃಷಿ ತಜ್ಞರನ್ನು ಸಂಪರ್ಕಿಸಿ.")
        })
        Row(verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(14.dp)) {
            Photo(s.photoPath,Modifier.size(82.dp),256);Column(Modifier.weight(1f)) {
                Text(s.selectedCrop.displayName(s.language),color=CropColors.Muted,fontSize=12.sp)
                Text(if(certain) title else s.tr("Leaf observation","ಎಲೆಯ ವೀಕ್ಷಣೆ"),fontSize=24.sp,fontWeight=FontWeight.Medium)
            }
        }
        val score=top?.score ?: stored?.score
        if(score!=null) ScoreCard(s,score,certain)
        if(!certain && (evidence?.ranked?.isNotEmpty()==true || condition!=null)) SoftCard {
            Text(s.tr("Possible — not confirmed","ಸಾಧ್ಯತೆ — ದೃಢಪಟ್ಟಿಲ್ಲ"),fontSize=15.sp,fontWeight=FontWeight.Medium)
            val ranked=evidence?.ranked?.take(2)
            if(ranked!=null) ranked.forEach {PredictionRow(it.condition.displayName(s.language),it.score)}
            else condition?.let {Text(it.displayName(s.language),fontSize=16.sp)}
        }
        if(result is AssessmentResult.Retake) SoftCard {Text(s.tr("Photo checks","ಫೋಟೋ ಪರಿಶೀಲನೆ"),fontSize=16.sp);result.quality.issues.forEach {Text("• "+qualityCopy(it,s),fontSize=13.sp,color=CropColors.Muted)}}
        if(certain) Row(horizontalArrangement=Arrangement.spacedBy(10.dp)) {
            MiniCard(s.tr("Concern check","ಲಕ್ಷಣ ಪರಿಶೀಲನೆ"),s.tr("Based on 3 questions","3 ಪ್ರಶ್ನೆಗಳ ಆಧಾರದಲ್ಲಿ"),Modifier.weight(1f))
            MiniCard(s.tr("Other signs?","ಬೇರೆ ಲಕ್ಷಣಗಳಿವೆಯೇ?"),s.tr("Check with an expert","ತಜ್ಞರನ್ನು ಸಂಪರ್ಕಿಸಿ"),Modifier.weight(1f))
        }
        AudioButton(s.prompt?.audioAsset ?: prompt("uncertain").audioAsset,s.tr("Listen in ${s.language.displayName}","ಕನ್ನಡದಲ್ಲಿ ಕೇಳಿ"),autoPlay=s.autoAudio)
        if(certain) {
            Primary(s.tr("Check concern (3 questions)","ಲಕ್ಷಣ ಪರಿಶೀಲನೆ (3 ಪ್ರಶ್ನೆಗಳು)"),{a(AppAction.Navigate(Screen.CONCERN))})
            Secondary(s.tr("See guidance","ಮಾರ್ಗದರ್ಶನ ನೋಡಿ"),{a(AppAction.Navigate(Screen.GUIDANCE))})
        } else {
            ExpertCall(s)
            Primary(s.tr("Retake photo","ಮತ್ತೆ ಫೋಟೋ ತೆಗೆಯಿರಿ"),{a(AppAction.Navigate(Screen.CAPTURE))},Icons.Outlined.CameraAlt)
            Secondary(s.tr("Observe symptoms (3 questions)","ಲಕ್ಷಣಗಳನ್ನು ಗಮನಿಸಿ (3 ಪ್ರಶ್ನೆಗಳು)"),{a(AppAction.Navigate(Screen.CONCERN))})
        }
        if(stored==null) Secondary(if(s.savedObservationId==null) s.tr("Save scan","ಪರಿಶೀಲನೆ ಉಳಿಸಿ") else s.tr("Saved on this phone","ಈ ಫೋನ್‌ನಲ್ಲಿ ಉಳಿಸಲಾಗಿದೆ"),{a(AppAction.SaveObservation)},Icons.Outlined.BookmarkBorder,enabled=s.savedObservationId==null && result!=null)
        Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.Center) {TextButton(onClick={a(AppAction.ShareCurrent)}) {Icon(Icons.Outlined.Share,null,Modifier.size(16.dp));Spacer(Modifier.width(6.dp));Text(s.tr("Share observation","ವೀಕ್ಷಣೆ ಹಂಚಿಕೊಳ್ಳಿ"))}}
        if(!certain) Text(s.tr("Prototype model: scores are not validated diagnostic probabilities.","ಪ್ರಾಯೋಗಿಕ ಮಾದರಿ: ಅಂಕಗಳು ದೃಢೀಕರಿಸಿದ ರೋಗನಿರ್ಣಯದ ಸಂಭವನೀಯತೆಗಳಲ್ಲ."),fontSize=11.sp,color=CropColors.Muted)
    }
}

@Composable private fun ScoreCard(s:AppUiState,score:Float,validated:Boolean) {
    SoftCard {
        Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween) {Text(if(validated) s.tr("Model confidence","ಮಾದರಿಯ ವಿಶ್ವಾಸ") else s.tr("Model score · unvalidated","ಮಾದರಿಯ ಅಂಕ · ದೃಢೀಕರಿಸಿಲ್ಲ"),fontSize=13.sp);Text("${(score.coerceIn(0f,1f)*100).roundToInt()}%",fontSize=17.sp,fontWeight=FontWeight.Medium)}
        LinearProgressIndicator(progress={score.coerceIn(0f,1f)},modifier=Modifier.fillMaxWidth().height(6.dp).clip(CircleShape),color=if(validated) CropColors.Green else CropColors.Gold,trackColor=CropColors.Border)
    }
}
@Composable private fun PredictionRow(label:String,score:Float) {Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween) {Text(label,Modifier.weight(1f),fontSize=14.sp);Text("${(score*100).roundToInt()}%",fontSize=13.sp,color=CropColors.Muted)}}
private fun qualityCopy(issue:QualityIssue,s:AppUiState)=when(issue) {QualityIssue.BLURRY->s.tr("Hold steady and focus on one leaf.","ಸ್ಥಿರವಾಗಿ ಹಿಡಿದು ಒಂದು ಎಲೆಯ ಮೇಲೆ ಕೇಂದ್ರೀಕರಿಸಿ.");QualityIssue.TOO_DARK->s.tr("Move into natural light.","ನೈಸರ್ಗಿಕ ಬೆಳಕಿಗೆ ಸರಿಸಿ.");QualityIssue.TOO_BRIGHT->s.tr("Avoid glare or direct flash.","ಪ್ರಖರ ಬೆಳಕು ಅಥವಾ ನೇರ ಫ್ಲ್ಯಾಶ್ ತಪ್ಪಿಸಿ.");QualityIssue.TOO_SMALL->s.tr("Choose a larger, closer photo.","ದೊಡ್ಡದಾದ ಹತ್ತಿರದ ಫೋಟೋ ಆಯ್ಕೆಮಾಡಿ.");QualityIssue.UNREADABLE->s.tr("This image could not be opened.","ಈ ಚಿತ್ರವನ್ನು ತೆರೆಯಲಾಗಲಿಲ್ಲ.")}

@Composable private fun GuidanceScreen(s:AppUiState,a:(AppAction)->Unit,prompt:(String)->Prompt) {
    val g=s.guidance
    Page {
        Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.End) {LanguageToggle(s,a)}
        Text(g?.name ?: s.tr("Observation guidance","ವೀಕ್ಷಣೆಯ ಮಾರ್ಗದರ್ಶನ"),fontSize=28.sp,fontWeight=FontWeight.Medium)
        Text(g?.summary ?: prompt("uncertain").message,fontSize=14.sp,color=CropColors.Muted)
        AudioButton(g?.audioAsset ?: prompt("uncertain").audioAsset,s.tr("Listen to guidance","ಮಾರ್ಗದರ್ಶನ ಕೇಳಿ"),autoPlay=s.autoAudio)
        GuidanceCard(s.tr("What to observe","ಗಮನಿಸಬೇಕಾದುದು"),g?.symptoms ?: listOf(s.tr("Take clear photos of the affected leaf and the whole plant.","ಪೀಡಿತ ಎಲೆ ಮತ್ತು ಇಡೀ ಸಸ್ಯದ ಸ್ಪಷ್ಟ ಫೋಟೋ ತೆಗೆಯಿರಿ.")),CropColors.Green)
        GuidanceCard(s.tr("What to do now","ಈಗ ಮಾಡಬೇಕಾದುದು"),g?.actions ?: listOf(s.tr("Ask a local agriculture expert before choosing a treatment.","ಚಿಕಿತ್ಸೆ ಆಯ್ಕೆ ಮಾಡುವ ಮೊದಲು ಸ್ಥಳೀಯ ಕೃಷಿ ತಜ್ಞರನ್ನು ಸಂಪರ್ಕಿಸಿ.")),CropColors.Gold)
        GuidanceCard(s.tr("Prevention & next steps","ತಡೆಗಟ್ಟುವಿಕೆ ಮತ್ತು ಮುಂದಿನ ಕ್ರಮಗಳು"),g?.prevention ?: listOf(s.tr("Observe nearby plants and record changes over time.","ಹತ್ತಿರದ ಸಸ್ಯಗಳನ್ನು ಗಮನಿಸಿ ಕಾಲಕ್ರಮೇಣ ಬದಲಾವಣೆಗಳನ್ನು ದಾಖಲಿಸಿ.")),CropColors.Rose)
        Text(g?.caution ?: s.tr("This prototype does not provide verified chemical dosage instructions.","ಈ ಪ್ರಾಯೋಗಿಕ ಆವೃತ್ತಿ ದೃಢೀಕರಿಸಿದ ರಾಸಾಯನಿಕ ಪ್ರಮಾಣ ಸೂಚನೆಗಳನ್ನು ನೀಡುವುದಿಲ್ಲ."),fontSize=12.sp,color=CropColors.Muted)
        ExpertCall(s)
    }
}
@Composable private fun GuidanceCard(title:String,items:List<String>,accent:Color) {
    Surface(shape=RoundedCornerShape(18.dp),color=CropColors.Lavender,modifier=Modifier.fillMaxWidth()) {Row {
        Box(Modifier.width(4.dp).heightIn(min=112.dp).background(accent));Column(Modifier.padding(16.dp),verticalArrangement=Arrangement.spacedBy(8.dp)) {Text(title,fontSize=16.sp,fontWeight=FontWeight.Medium);items.forEach {Text("• $it",fontSize=13.sp,color=CropColors.Muted)}}
    }}}

@Composable private fun ConcernScreen(s:AppUiState,a:(AppAction)->Unit,prompt:(String)->Prompt) {
    var question by rememberSaveable {mutableIntStateOf(0)}
    var selected by rememberSaveable {mutableIntStateOf(-1)}
    val questions=listOf(
        s.tr("Are the symptoms spreading quickly?","ಲಕ್ಷಣಗಳು ಬೇಗ ಹರಡುತ್ತಿವೆಯೇ?"),
        s.tr("How much of the leaf looks affected?","ಎಲೆಯ ಎಷ್ಟು ಭಾಗ ಪೀಡಿತವಾಗಿ ಕಾಣುತ್ತದೆ?"),
        s.tr("Are many plants affected?","ಅನೇಕ ಸಸ್ಯಗಳು ಪೀಡಿತವಾಗಿವೆಯೇ?"),
    )
    val keys=listOf("concern_spreading","concern_coverage","concern_plants")
    if(question>=3) Page {
        Text(s.tr("Your observation summary","ನಿಮ್ಮ ವೀಕ್ಷಣೆಯ ಸಾರಾಂಶ"),fontSize=28.sp,fontWeight=FontWeight.Medium)
        val expert=s.concern.level==ConcernLevel.SEEK_LOCAL_EXPERT
        Notice(s.tr("Based on your answers","ನಿಮ್ಮ ಉತ್ತರಗಳ ಆಧಾರದಲ್ಲಿ"),if(expert)
            s.tr("Ask a local agriculture expert to review these signs.","ಈ ಲಕ್ಷಣಗಳನ್ನು ಪರಿಶೀಲಿಸಲು ಸ್ಥಳೀಯ ಕೃಷಿ ತಜ್ಞರನ್ನು ಸಂಪರ್ಕಿಸಿ.")
            else s.tr("Keep observing and recheck. Ask an expert if symptoms change or spread.","ಗಮನಿಸುತ್ತಿರಿ ಮತ್ತು ಮರುಪರಿಶೀಲಿಸಿ. ಲಕ್ಷಣಗಳು ಬದಲಾದರೆ ಅಥವಾ ಹರಡಿದರೆ ತಜ್ಞರನ್ನು ಸಂಪರ್ಕಿಸಿ."))
        Text(s.tr("This is a symptom checklist, not a photo-based severity diagnosis.","ಇದು ಲಕ್ಷಣಗಳ ಪಟ್ಟಿ, ಫೋಟೋ ಆಧಾರಿತ ತೀವ್ರತೆಯ ರೋಗನಿರ್ಣಯವಲ್ಲ."),fontSize=13.sp,color=CropColors.Muted)
        AudioButton(prompt(if(expert) "concern_expert" else "concern_observe").audioAsset,s.tr("Listen to the summary","ಸಾರಾಂಶ ಕೇಳಿ"))
        ExpertCall(s)
        Primary(s.tr("See observation guidance","ವೀಕ್ಷಣೆಯ ಮಾರ್ಗದರ್ಶನ ನೋಡಿ"),{a(AppAction.Navigate(Screen.GUIDANCE))})
    } else Page {
        Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween) {
            Text(s.tr("Symptom check","ಲಕ್ಷಣ ಪರಿಶೀಲನೆ"),fontSize=14.sp,color=CropColors.Muted)
            Text(s.tr("Question ${question+1} of 3","ಪ್ರಶ್ನೆ ${question+1} / 3"),fontSize=12.sp,color=CropColors.Primary)
        }
        LinearProgressIndicator(progress={(question+1)/3f},modifier=Modifier.fillMaxWidth(),color=CropColors.Primary,trackColor=CropColors.Lavender)
        Text(s.selectedCrop.displayName(s.language),fontSize=13.sp,color=CropColors.Muted)
        Text(questions[question],fontSize=28.sp,fontWeight=FontWeight.Medium)
        AudioButton(prompt(keys[question]).audioAsset,s.tr("Read question aloud","ಪ್ರಶ್ನೆಯನ್ನು ಕೇಳಿ"))
        val options=if(question==1) listOf(s.tr("A few spots","ಕೆಲವು ಚುಕ್ಕೆಗಳು"),s.tr("Some of the leaf","ಎಲೆಯ ಸ್ವಲ್ಪ ಭಾಗ"),s.tr("Much of the leaf","ಎಲೆಯ ಹೆಚ್ಚಿನ ಭಾಗ"),s.tr("I'm not sure","ಖಚಿತವಿಲ್ಲ"))
            else listOf(s.tr("Yes","ಹೌದು"),s.tr("No","ಇಲ್ಲ"),s.tr("I'm not sure","ಖಚಿತವಿಲ್ಲ"))
        options.forEachIndexed {index,label ->
            Surface(onClick={selected=index},shape=RoundedCornerShape(18.dp),color=if(selected==index) CropColors.Lavender else Color.White,
                border=BorderStroke(if(selected==index) 1.5.dp else 1.dp,if(selected==index) CropColors.Primary else CropColors.Border),modifier=Modifier.fillMaxWidth()) {
                Row(Modifier.padding(horizontal=16.dp,vertical=10.dp),verticalAlignment=Alignment.CenterVertically) {
                    RadioButton(selected=selected==index,onClick={selected=index});Spacer(Modifier.width(12.dp));Text(label,fontSize=17.sp)
                }
            }
        }
        Primary(s.tr(if(question==2) "See summary" else "Next",if(question==2) "ಸಾರಾಂಶ ನೋಡಿ" else "ಮುಂದೆ"),{
            val uncertain=selected==options.lastIndex
            val next=when(question) {
                0 ->s.symptoms.copy(spreadingQuickly=selected==0,uncertainAnswers=s.symptoms.uncertainAnswers || uncertain)
                1 ->s.symptoms.copy(leafCoverage=when(selected) {0->LeafCoverage.FEW_SPOTS;1->LeafCoverage.SOME_SPOTS;2->LeafCoverage.MANY_SPOTS;else->LeafCoverage.NOT_REPORTED},uncertainAnswers=s.symptoms.uncertainAnswers || uncertain)
                else ->s.symptoms.copy(manyPlantsAffected=selected==0,uncertainAnswers=s.symptoms.uncertainAnswers || uncertain)
            }
            a(AppAction.ReportSymptoms(next));question++;selected=-1
        },Icons.Outlined.ArrowForward,enabled=selected>=0)
        Text(s.tr("Your answers describe what you see; they do not confirm a disease.","ನಿಮ್ಮ ಉತ್ತರಗಳು ನೀವು ಗಮನಿಸಿದುದನ್ನು ವಿವರಿಸುತ್ತವೆ; ರೋಗವನ್ನು ದೃಢಪಡಿಸುವುದಿಲ್ಲ."),fontSize=12.sp,color=CropColors.Muted)
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
@Composable private fun HistoryCard(o:Observation,s:AppUiState,a:(AppAction)->Unit) {
    Surface(shape=RoundedCornerShape(18.dp),color=CropColors.Lavender,modifier=Modifier.fillMaxWidth().clickable {a(AppAction.OpenObservation(o.id))}) {
        Row(Modifier.padding(12.dp),verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(12.dp)) {
            Photo(o.imagePath,Modifier.size(60.dp),160);Column(Modifier.weight(1f),verticalArrangement=Arrangement.spacedBy(4.dp)) {
                Text(if(o.validated) Conditions.byId(o.conditionId.orEmpty())?.displayName(s.language) ?: s.tr("Leaf observation","ಎಲೆಯ ವೀಕ್ಷಣೆ") else s.tr("Needs review","ಪರಿಶೀಲನೆ ಅಗತ್ಯ"),fontSize=15.sp,fontWeight=FontWeight.Medium)
                Text(o.crop.displayName(s.language)+" · "+SimpleDateFormat("h:mm a",Locale.getDefault()).format(Date(o.createdAt)),fontSize=11.sp,color=CropColors.Muted)
                Text(if(o.validated) s.tr("Model assessment","ಮಾದರಿಯ ಪರಿಶೀಲನೆ") else s.tr("Uncertain observation","ಅನಿಶ್ಚಿತ ವೀಕ್ಷಣೆ"),fontSize=10.sp,color=CropColors.Gold)
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

@Composable fun AudioButton(asset:String?,label:String,autoPlay:Boolean=false) {
    val context=LocalContext.current;var player by remember {mutableStateOf<MediaPlayer?>(null)};var playing by remember {mutableStateOf(false)};var failed by remember {mutableStateOf(false)}
    val unavailable=when(LocalAppLanguage.current) {AppLanguage.ENGLISH -> "Audio unavailable";AppLanguage.KANNADA -> "ಧ್ವನಿ ಲಭ್ಯವಿಲ್ಲ";AppLanguage.HINDI -> HindiUi.translate("Audio unavailable")}
    fun stop() { player?.let { current -> runCatching { current.stop() }; current.release() }; player=null;playing=false }
    fun play() {
        if(asset==null) return
        stop();failed=false
        runCatching {
            val afd=context.assets.openFd(asset);val next=MediaPlayer();next.setDataSource(afd.fileDescriptor,afd.startOffset,afd.length);afd.close();player=next
            next.setOnCompletionListener {playing=false;it.release();if(player===it) player=null}
            next.setOnErrorListener {p,_,_->playing=false;failed=true;p.release();if(player===p) player=null;true}
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
