package com.debuggers.crophealth.ui

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.debuggers.crophealth.domain.AppLanguage
import com.debuggers.crophealth.presentation.*
import java.io.File

@Composable
fun CameraScreen(state:AppUiState,onAction:(AppAction)->Unit,newCameraFile:()->File) {
    val context=LocalContext.current;val owner=LocalLifecycleOwner.current
    var permitted by remember {mutableStateOf(ContextCompat.checkSelfPermission(context,Manifest.permission.CAMERA)==PackageManager.PERMISSION_GRANTED)}
    val permission=rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {permitted=it}
    val gallery=rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) {uri->uri?.let {onAction(AppAction.ImportPhoto(it))}}
    var imageCapture by remember {mutableStateOf<ImageCapture?>(null)};var flash by remember {mutableStateOf(false)};var capturing by remember {mutableStateOf(false)};var error by remember {mutableStateOf<String?>(null)}
    val preview=remember {PreviewView(context).apply {scaleType=PreviewView.ScaleType.FILL_CENTER}}
    DisposableEffect(permitted) {
        var provider:ProcessCameraProvider?=null
        var disposed=false
        if(permitted) {
            val future=ProcessCameraProvider.getInstance(context)
            future.addListener(listener@{
                if(disposed) return@listener
                runCatching {
                    val p=future.get();provider=p;val view=androidx.camera.core.Preview.Builder().build().also {it.surfaceProvider=preview.surfaceProvider}
                    val capture=ImageCapture.Builder().setCaptureMode(ImageCapture.CAPTURE_MODE_MINIMIZE_LATENCY).build();imageCapture=capture
                    p.unbindAll();p.bindToLifecycle(owner,CameraSelector.DEFAULT_BACK_CAMERA,view,capture)
                }.onFailure {error="Camera unavailable. You can choose a photo from your gallery."}
            },ContextCompat.getMainExecutor(context))
        }
        onDispose {disposed=true;provider?.unbindAll();imageCapture=null}
    }
    fun capture() {
        val c=imageCapture?:return;capturing=true;error=null
        c.flashMode=if(flash) ImageCapture.FLASH_MODE_ON else ImageCapture.FLASH_MODE_OFF
        val file=newCameraFile()
        c.takePicture(ImageCapture.OutputFileOptions.Builder(file).build(),ContextCompat.getMainExecutor(context),object:ImageCapture.OnImageSavedCallback {
            override fun onImageSaved(output:ImageCapture.OutputFileResults) {capturing=false;onAction(AppAction.CameraCaptured(file))}
            override fun onError(exception:ImageCaptureException) {capturing=false;error="Photo could not be captured. Please try again.";file.delete()}
        })
    }
    Surface(color=CropColors.Camera,modifier=Modifier.fillMaxSize()) {
        BoxWithConstraints(Modifier.fillMaxSize().statusBarsPadding().navigationBarsPadding().padding(20.dp)) {
        val gap=if(maxHeight<540.dp) 10.dp else 20.dp
        val needsScroll=maxHeight<360.dp || (error!=null && maxHeight<420.dp)
        val reserved=189.dp+gap*5+(if(error!=null) 56.dp else 0.dp)
        val frameHeight=minOf(maxHeight*.43f,370.dp,(maxHeight-reserved).coerceAtLeast(100.dp))
        val columnModifier=if(needsScroll) Modifier.fillMaxSize().verticalScroll(rememberScrollState()) else Modifier.fillMaxSize()
        Column(columnModifier,verticalArrangement=Arrangement.spacedBy(gap)) {
            Row(Modifier.fillMaxWidth(),verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.SpaceBetween) {
                IconButton(onClick={onAction(AppAction.Navigate(Screen.HOME))}) {Icon(Icons.Outlined.Close,"Close camera",tint=Color.White)}
                Surface(shape=RoundedCornerShape(20.dp),color=CropColors.Tomato) {Text(if(state.language==AppLanguage.KANNADA) state.selectedCrop.nameKn else state.selectedCrop.nameEn,color=Color.White,fontSize=12.sp,modifier=Modifier.padding(horizontal=18.dp,vertical=8.dp))}
                TextButton(onClick={flash=!flash}) {Text(if(flash) "Flash on" else "Flash off",fontSize=11.sp,color=Color.White)}
            }
            Box(Modifier.fillMaxWidth().height(frameHeight).clip(RoundedCornerShape(24.dp)).background(Color(0xFF2E3B31)).border(1.dp,Color.White.copy(alpha=.5f),RoundedCornerShape(24.dp)),contentAlignment=Alignment.Center) {
                if(permitted) AndroidView(factory={preview},modifier=Modifier.fillMaxSize())
                else Column(Modifier.padding(24.dp),horizontalAlignment=Alignment.CenterHorizontally,verticalArrangement=Arrangement.spacedBy(16.dp)) {
                    Icon(Icons.Outlined.CameraAlt,null,tint=Color.White,modifier=Modifier.size(50.dp))
                    Text("Allow camera access to photograph a leaf, or choose one from your gallery.",color=Color.White,textAlign=androidx.compose.ui.text.style.TextAlign.Center,fontSize=14.sp)
                    Button(onClick={permission.launch(Manifest.permission.CAMERA)}) {Text("Allow camera")}
                }
                Box(Modifier.fillMaxSize().padding(16.dp).border(1.dp,Color.White.copy(alpha=.65f),RoundedCornerShape(17.dp)))
            }
            Text(if(state.language==AppLanguage.KANNADA) "ಒಂದು ಎಲೆ ಚೌಕಟ್ಟಿನೊಳಗೆ ಇರಲಿ" else "Fit one leaf inside the frame",color=Color.White,fontSize=15.sp,modifier=Modifier.align(Alignment.CenterHorizontally))
            Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.Center) {listOf("Good light","Hold steady","Close up").forEach {Text(it,color=Color(0xFFD5CBDF),fontSize=10.sp,modifier=Modifier.padding(horizontal=6.dp).clip(RoundedCornerShape(20.dp)).background(Color.White.copy(alpha=.08f)).padding(horizontal=10.dp,vertical=7.dp))}}
            error?.let {Text(it,color=Color(0xFFFFCE9A),fontSize=12.sp)}
            Spacer(if(needsScroll) Modifier.height(8.dp) else Modifier.weight(1f))
            Row(Modifier.fillMaxWidth().padding(vertical=10.dp),horizontalArrangement=Arrangement.SpaceAround,verticalAlignment=Alignment.CenterVertically) {
                IconButton(onClick={gallery.launch("image/*")},modifier=Modifier.size(48.dp).clip(RoundedCornerShape(13.dp)).background(Color.White.copy(alpha=.1f))) {Icon(Icons.Outlined.PhotoLibrary,"Choose photo",tint=Color.White)}
                Box(Modifier.size(78.dp).clip(CircleShape).border(5.dp,Color(0xFFD7C8ED),CircleShape).padding(9.dp).clip(CircleShape).background(Color.White).clickable(enabled=permitted && imageCapture!=null && !capturing) {capture()},contentAlignment=Alignment.Center) {if(capturing) CircularProgressIndicator(Modifier.size(25.dp),strokeWidth=2.dp)}
                IconButton(onClick={onAction(AppAction.SetLanguage(if(state.language==AppLanguage.ENGLISH) AppLanguage.KANNADA else AppLanguage.ENGLISH))},modifier=Modifier.size(48.dp).background(Color.White.copy(alpha=.1f),CircleShape)) {Text(if(state.language==AppLanguage.ENGLISH) "ಕ" else "EN",color=Color.White,fontSize=16.sp)}
            }
        }
        }
    }
}
