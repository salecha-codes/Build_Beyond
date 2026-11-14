package com.debuggers.crophealth.inference

import android.graphics.*
import androidx.exifinterface.media.ExifInterface
import com.debuggers.crophealth.domain.QualityMetrics
import java.io.File
import kotlin.math.floor
import kotlin.math.max
import kotlin.math.min

data class PreparedPhoto(val bitmap: Bitmap, val quality: QualityMetrics)

object ImagePreparation {
    /** Bounded decode prevents full-resolution camera images exhausting a budget phone's heap. */
    fun decode(file: File, maxSide: Int = 1024): PreparedPhoto {
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeFile(file.path, bounds)
        require(bounds.outWidth > 0 && bounds.outHeight > 0) { "This file is not a readable photo." }
        var sample = 1
        while (max(bounds.outWidth, bounds.outHeight) / sample > maxSide) sample *= 2
        val bitmap = BitmapFactory.decodeFile(file.path, BitmapFactory.Options().apply {
            inSampleSize = sample; inPreferredConfig = Bitmap.Config.ARGB_8888
        }) ?: error("This photo could not be decoded.")
        val orientation = runCatching { ExifInterface(file).getAttributeInt(ExifInterface.TAG_ORIENTATION, 1) }.getOrDefault(1)
        val matrix = Matrix().apply {
            when (orientation) {
                2 -> postScale(-1f, 1f)
                3 -> postRotate(180f)
                4 -> postScale(1f, -1f)
                5 -> { postRotate(90f); postScale(-1f, 1f) }
                6 -> postRotate(90f)
                7 -> { postRotate(270f); postScale(-1f, 1f) }
                8 -> postRotate(270f)
            }
        }
        val normalized = if (matrix.isIdentity) bitmap else Bitmap.createBitmap(bitmap, 0, 0, bitmap.width, bitmap.height, matrix, true).also {
            if (it !== bitmap) bitmap.recycle()
        }
        return PreparedPhoto(normalized, measureQuality(normalized))
    }

    fun measureQuality(bitmap: Bitmap): QualityMetrics {
        val scale = min(1f, 256f / max(bitmap.width, bitmap.height))
        val small = Bitmap.createScaledBitmap(bitmap, max(1, (bitmap.width * scale).toInt()), max(1, (bitmap.height * scale).toInt()), true)
        val width = small.width; val height = small.height
        val pixels = IntArray(width * height)
        small.getPixels(pixels, 0, width, 0, 0, width, height)
        val luminance = DoubleArray(pixels.size) { i ->
            val c = pixels[i]; .2126 * Color.red(c) + .7152 * Color.green(c) + .0722 * Color.blue(c)
        }
        var sum = 0.0; var squared = 0.0; var count = 0
        for (y in 1 until height - 1) for (x in 1 until width - 1) {
            val i = y * width + x
            val laplacian = luminance[i - 1] + luminance[i + 1] + luminance[i - width] + luminance[i + width] - 4 * luminance[i]
            sum += laplacian; squared += laplacian * laplacian; count++
        }
        if (small !== bitmap) small.recycle()
        val variance = if (count == 0) 0.0 else max(0.0, squared / count - (sum / count) * (sum / count))
        return QualityMetrics(luminance.average(), variance, bitmap.width, bitmap.height)
    }

    fun tensor(bitmap: Bitmap, spec: InputSpec): FloatArray {
        val scale = min(spec.width.toDouble() / bitmap.width, spec.height.toDouble() / bitmap.height)
        val newWidth = max(1, floor(bitmap.width * scale + .5).toInt())
        val newHeight = max(1, floor(bitmap.height * scale + .5).toInt())
        val source = IntArray(bitmap.width * bitmap.height)
        bitmap.getPixels(source, 0, bitmap.width, 0, 0, bitmap.width, bitmap.height)
        // Match Pillow's antialiased bilinear preprocessing used by training/export.
        val scaled = PillowBilinear.resizeRgb(source, bitmap.width, bitmap.height, newWidth, newHeight)
        val pixels = IntArray(spec.width * spec.height) { Color.rgb(spec.padding[0], spec.padding[1], spec.padding[2]) }
        val offsetX = (spec.width - newWidth) / 2
        val offsetY = (spec.height - newHeight) / 2
        for (y in 0 until newHeight) {
            scaled.copyInto(pixels, (y + offsetY) * spec.width + offsetX, y * newWidth, (y + 1) * newWidth)
        }
        val output = FloatArray(pixels.size * 3)
        for (i in pixels.indices) {
            output[i] = (Color.red(pixels[i]) / spec.pixelScale - spec.mean[0]) / spec.std[0]
            output[pixels.size + i] = (Color.green(pixels[i]) / spec.pixelScale - spec.mean[1]) / spec.std[1]
            output[2 * pixels.size + i] = (Color.blue(pixels[i]) / spec.pixelScale - spec.mean[2]) / spec.std[2]
        }
        return output
    }
}

data class InputSpec(
    val name: String,
    val width: Int,
    val height: Int,
    val mean: FloatArray,
    val std: FloatArray,
    val padding: IntArray,
    val pixelScale: Float,
)
