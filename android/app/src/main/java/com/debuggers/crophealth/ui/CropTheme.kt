package com.debuggers.crophealth.ui

import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.unit.dp

/** Tokens transcribed from the user's eight Figma screen exports. */
object CropColors {
    val Ink = Color(0xFF251448)
    val Primary = Color(0xFF4E2C99)
    val Lavender = Color(0xFFF6F2FB)
    val Chip = Color(0xFFEFEAF6)
    val Muted = Color(0xFF81798B)
    val Border = Color(0xFFE8E2F0)
    val Green = Color(0xFF397657)
    val Gold = Color(0xFFC08A2E)
    val PaleGold = Color(0xFFFFF6E4)
    val Rose = Color(0xFFB97079)
    val Camera = Color(0xFF1D1530)
    val Tomato = Color(0xFFB57742)
}

@Composable
fun CropTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = lightColorScheme(primary=CropColors.Primary, onPrimary=Color.White,
            background=Color.White, onBackground=CropColors.Ink, surface=Color.White,
            onSurface=CropColors.Ink, surfaceVariant=CropColors.Lavender,
            onSurfaceVariant=CropColors.Muted, outline=CropColors.Border),
        shapes=Shapes(small=RoundedCornerShape(12.dp), medium=RoundedCornerShape(18.dp), large=RoundedCornerShape(24.dp)),
        content=content,
    )
}
