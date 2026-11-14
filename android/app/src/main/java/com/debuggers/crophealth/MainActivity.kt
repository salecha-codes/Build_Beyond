package com.debuggers.crophealth

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.lifecycle.viewmodel.compose.viewModel
import com.debuggers.crophealth.presentation.CropHealthViewModel
import com.debuggers.crophealth.ui.CropHealthApp

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { val model: CropHealthViewModel = viewModel(); CropHealthApp(model) }
    }
}
