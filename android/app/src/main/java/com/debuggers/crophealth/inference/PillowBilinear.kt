package com.debuggers.crophealth.inference

import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min

/**
 * RGB resize matching Pillow's separable antialiased BILINEAR convention.
 *
 * Algorithm reference: python-pillow/Pillow 13.0.0,
 * https://github.com/python-pillow/Pillow/blob/13.0.0/src/libImaging/Resample.c
 *
 * Downsampling widens the triangle filter by the scale factor. Each axis uses
 * normalized 22-bit coefficients and rounds to an 8-bit intermediate, horizontal
 * before vertical. This differs from Skia's generic filtered bitmap resize.
 * Input alpha is ignored, as with the training pipeline's conversion to RGB.
 */
object PillowBilinear {
    private const val PRECISION = 22
    private const val UNIT = 1 shl PRECISION
    private const val ROUND = 1 shl (PRECISION - 1)

    private data class Weights(val first: Int, val coefficients: IntArray)

    private fun coefficients(inputSize: Int, outputSize: Int): Array<Weights> {
        val scale = inputSize.toDouble() / outputSize
        val filterScale = max(1.0, scale)
        val support = filterScale // Bilinear triangle has unit support.
        val inverse = 1.0 / filterScale
        return Array(outputSize) { index ->
            val center = (index + 0.5) * scale
            // toInt truncates toward zero, matching the source C convention.
            val first = max(0, (center - support + 0.5).toInt())
            val end = min(inputSize, (center + support + 0.5).toInt())
            val floating = DoubleArray(end - first) { offset ->
                max(0.0, 1.0 - abs((offset + first - center + 0.5) * inverse))
            }
            val total = floating.sum()
            check(total > 0.0) { "Empty interpolation kernel" }
            Weights(first, IntArray(floating.size) { offset ->
                (floating[offset] / total * UNIT + 0.5).toInt()
            })
        }
    }

    private fun channel(sum: Int): Int = (sum shr PRECISION).coerceIn(0, 255)

    private fun opaqueRgb(red: Int, green: Int, blue: Int): Int =
        (0xff shl 24) or (red shl 16) or (green shl 8) or blue

    /** Returns opaque packed ARGB without changing the caller's input array. */
    fun resizeRgb(
        pixels: IntArray,
        width: Int,
        height: Int,
        newWidth: Int,
        newHeight: Int,
    ): IntArray {
        require(width > 0 && height > 0 && newWidth > 0 && newHeight > 0)
        require(width.toLong() * height == pixels.size.toLong())
        require(newWidth.toLong() * height <= Int.MAX_VALUE)
        require(newWidth.toLong() * newHeight <= Int.MAX_VALUE)

        val horizontal = if (width == newWidth) {
            // Pillow skips an unchanged axis; retain its exact source bytes.
            pixels
        } else {
            val weights = coefficients(width, newWidth)
            IntArray(newWidth * height).also { result ->
                for (y in 0 until height) {
                    val sourceRow = y * width
                    val outputRow = y * newWidth
                    for (x in 0 until newWidth) {
                        val kernel = weights[x]
                        var red = ROUND
                        var green = ROUND
                        var blue = ROUND
                        for (offset in kernel.coefficients.indices) {
                            val pixel = pixels[sourceRow + kernel.first + offset]
                            val weight = kernel.coefficients[offset]
                            red += ((pixel ushr 16) and 255) * weight
                            green += ((pixel ushr 8) and 255) * weight
                            blue += (pixel and 255) * weight
                        }
                        result[outputRow + x] = opaqueRgb(channel(red), channel(green), channel(blue))
                    }
                }
            }
        }

        if (height == newHeight) {
            return IntArray(horizontal.size) { horizontal[it] or (0xff shl 24) }
        }
        val verticalWeights = coefficients(height, newHeight)
        return IntArray(newWidth * newHeight).also { result ->
            for (y in 0 until newHeight) {
                val kernel = verticalWeights[y]
                for (x in 0 until newWidth) {
                    var red = ROUND
                    var green = ROUND
                    var blue = ROUND
                    for (offset in kernel.coefficients.indices) {
                        val pixel = horizontal[(kernel.first + offset) * newWidth + x]
                        val weight = kernel.coefficients[offset]
                        red += ((pixel ushr 16) and 255) * weight
                        green += ((pixel ushr 8) and 255) * weight
                        blue += (pixel and 255) * weight
                    }
                    result[y * newWidth + x] = opaqueRgb(channel(red), channel(green), channel(blue))
                }
            }
        }
    }
}
