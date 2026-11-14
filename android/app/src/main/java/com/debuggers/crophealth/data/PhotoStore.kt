package com.debuggers.crophealth.data

import android.content.Context
import android.net.Uri
import java.io.File
import java.util.UUID

class PhotoStore(private val context: Context) {
    private val directory = File(context.filesDir, "observations").apply { mkdirs() }
    fun newCameraFile(): File = File(directory, "${UUID.randomUUID()}.jpg")

    fun importPhoto(uri: Uri): File {
        val output = File(directory, "${UUID.randomUUID()}.image")
        try {
            val stream = context.contentResolver.openInputStream(uri) ?: error("The photo could not be opened.")
            stream.use { source -> output.outputStream().use { target ->
                val buffer = ByteArray(8192); var total = 0L
                while (true) {
                    val count = source.read(buffer)
                    if (count < 0) break
                    total += count
                    require(total <= 25L * 1024 * 1024) { "This photo is too large. Please select a smaller image." }
                    target.write(buffer, 0, count)
                }
                require(total > 0) { "The selected file is empty." }
            } }
            return output
        } catch (failure: Exception) { output.delete(); throw failure }
    }
}
