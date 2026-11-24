package dev.niels.jarvis

import android.content.ActivityNotFoundException
import android.content.ClipData
import android.content.ClipboardManager
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import android.os.Build
import android.os.RemoteException
import android.os.ext.SdkExtensions
import android.util.Size
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.platform.LocalContext
import androidx.core.content.FileProvider
import androidx.pdf.PdfPasswordException
import androidx.pdf.SandboxedPdfLoader
import java.io.File
import java.io.IOException
import java.nio.file.Files
import java.nio.file.StandardCopyOption.ATOMIC_MOVE
import java.nio.file.StandardCopyOption.REPLACE_EXISTING
import kotlin.math.ceil
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.Response

class VerifiedFileProvider : FileProvider(R.xml.file_paths)

private sealed interface Original {
    data class Ready(val file: File, val name: String, val mime: String) : Original
    data class Missing(val reason: String) : Original
}

@Composable
internal fun FilePane(
    route: Route.File,
    api: HomeApi,
    reload: Pair<Int, Int>,
    signIn: () -> Unit,
    discuss: (DiscussionRef?) -> Unit,
) {
    val context = LocalContext.current
    var page by rememberSaveable(route.id, route.page) { mutableLongStateOf(route.page ?: 1L) }
    var fileActionStatus by remember { mutableStateOf<String?>(null) }
    Read(route.id, reload, signIn, { readOriginal(context, api, route.id) }) { original ->
        Pane {
            when (original) {
                is Original.Missing -> BodyStatus(original.reason)
                is Original.Ready -> {
                    val file = original.file
                    val pdf = original.mime == "application/pdf"
                    val image = original.mime.startsWith("image/")
                    Heading(original.name)
                    val preview by produceState<Preview?>(null, original, page) {
                        value = null
                        if (pdf || image) value = previewOriginal(context, original, page)
                    }
                    val displayed = preview
                    if (pdf || image) {
                        when {
                            displayed == null -> CircularProgressIndicator()
                            displayed.problem != null -> BodyStatus(displayed.problem)
                            displayed.bitmap != null -> Image(
                                displayed.bitmap.asImageBitmap(),
                                if (pdf) "${original.name}, page $page of ${displayed.pages}" else original.name,
                                Modifier.fillMaxWidth(),
                            )
                        }
                    }
                    if (pdf && displayed != null && displayed.pages > 0) {
                        FlowRow {
                            TextButton(enabled = page > 1, onClick = { page = if (page > displayed.pages) 1 else page - 1 }) {
                                Text(if (page > displayed.pages) "open first page" else "previous page")
                            }
                            TextButton(enabled = page < displayed.pages, onClick = { page++ }) { Text("next page") }
                        }
                        if (page <= displayed.pages) Text("page $page of ${displayed.pages}")
                    }
                    val allowedPage = page.takeIf { pdf && displayed?.bitmap != null && displayed.page == page }
                    val ref = DiscussionRef.File(route.id, allowedPage)
                    FlowRow {
                        if (!pdf || allowedPage != null) {
                            TextButton(onClick = { discuss(ref) }) { Text(if (pdf) "ask about this page" else "ask about this file") }
                        }
                        TextButton(onClick = {
                            val privateUri = Routes.url(Route.File(route.id, page.takeIf { pdf }))
                            context.getSystemService(ClipboardManager::class.java)
                                .setPrimaryClip(ClipData.newPlainText("private jarvis link", privateUri.toString()))
                            fileActionStatus = "private link copied"
                        }) { Text("copy private link") }
                        TextButton(onClick = {
                            fileActionStatus = try {
                                val uri = FileProvider.getUriForFile(context, "${context.packageName}.files", file, original.name)
                                val send = Intent(Intent.ACTION_SEND)
                                    .setType(original.mime)
                                    .putExtra(Intent.EXTRA_STREAM, uri)
                                    .apply { clipData = ClipData.newUri(context.contentResolver, original.name, uri) }
                                    .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                                val chooser = Intent.createChooser(send, null).putExtra(
                                    Intent.EXTRA_EXCLUDE_COMPONENTS,
                                    arrayOf(ComponentName(context, ShareActivity::class.java)),
                                )
                                context.startActivity(chooser)
                                null
                            } catch (_: ActivityNotFoundException) {
                                "no app can receive this copy"
                            } catch (_: IllegalArgumentException) {
                                "verified file copy unavailable · refresh"
                            }
                        }) { Text("share a file copy") }
                    }
                    fileActionStatus?.let { BodyStatus(it) }
                }
                null -> BodyStatus("original unavailable")
            }
        }
    }
}

private data class Preview(val page: Long, val bitmap: Bitmap? = null, val pages: Int = 0, val problem: String? = null)

private suspend fun previewOriginal(context: Context, original: Original.Ready, number: Long): Preview =
    withContext(Dispatchers.IO) {
        val file = original.file
        try {
            if (original.mime == "application/pdf") {
                if (SdkExtensions.getExtensionVersion(Build.VERSION_CODES.S) < 13) {
                    return@withContext Preview(number, problem = "pdf preview needs an android system update")
                }
                val uri = FileProvider.getUriForFile(context, "${context.packageName}.files", file)
                SandboxedPdfLoader(context).openDocument(uri, password = null).use { document ->
                    val count = document.pageCount
                    if (number !in 1L..count.toLong()) {
                        return@withContext Preview(number, pages = count, problem = "page no longer available")
                    }
                    val index = number.toInt() - 1
                    val page = document.getPageInfo(index)
                    if (page.width <= 0 || page.height <= 0) {
                        return@withContext Preview(number, pages = count, problem = "preview unavailable")
                    }
                    val scale = minOf(1600.0 / page.width, 2400.0 / page.height)
                    val width = ceil(page.width * scale).toInt().coerceAtLeast(1)
                    val height = ceil(page.height * scale).toInt().coerceAtLeast(1)
                    document.getPageBitmapSource(index).use { source ->
                        Preview(number, source.getBitmap(Size(width, height)), count)
                    }
                }
            } else {
                val options = BitmapFactory.Options().apply { inJustDecodeBounds = true }
                BitmapFactory.decodeFile(file.path, options)
                val span = maxOf(options.outWidth, options.outHeight)
                options.inSampleSize = 1
                while (span / options.inSampleSize > 1600) options.inSampleSize *= 2
                options.inJustDecodeBounds = false
                val bitmap = BitmapFactory.decodeFile(file.path, options)
                Preview(number, bitmap, problem = if (bitmap == null) "preview unavailable" else null)
            }
        } catch (_: PdfPasswordException) {
            Preview(number, problem = "password-protected pdf · share a copy to open it separately")
        } catch (failure: RuntimeException) {
            if (failure is kotlinx.coroutines.CancellationException) throw failure
            Preview(number, problem = "preview unavailable")
        } catch (_: IOException) {
            Preview(number, problem = "preview unavailable")
        } catch (_: RemoteException) {
            Preview(number, problem = "preview unavailable")
        }
    }

private suspend fun readOriginal(context: Context, api: HomeApi, id: String): Original = withContext(Dispatchers.IO) {
    val path = "/api/files/$id"
    val directory = File(context.cacheDir, "verified/$id")
    fun missing(response: Response): Original.Missing? = when (response.code) {
        404, 410 -> {
            if (!directory.deleteRecursively()) throw IOException("could not remove stale file copy")
            Original.Missing(if (response.code == 410) "original deleted" else "original not found")
        }
        409 -> Original.Missing(
            if (response.header("X-Jarvis-File-State") == "Pending") "saving original" else "original unavailable",
        )
        else -> null
    }
    val metadata = api.request(path, "HEAD").use { response ->
        missing(response)?.let { return@withContext it }
        if (!response.isSuccessful) throw IOException("could not read original metadata")
        val type = response.header("Content-Type")?.substringBefore(';') ?: "application/octet-stream"
        val length = response.header("Content-Length")?.toLongOrNull()?.takeIf { it >= 0 }
            ?: throw IOException("unknown original size")
        val encoded = response.header("Content-Disposition")?.substringAfter("filename*=utf-8''", "")
        val name = displayFileName(encoded?.let(Uri::decode), "original")
        Triple(name, type, length)
    }
    val (name, type, length) = metadata
    val suffix = when (type) {
        "application/pdf" -> ".pdf"
        "image/png" -> ".png"
        "image/jpeg" -> ".jpg"
        "image/gif" -> ".gif"
        "image/webp" -> ".webp"
        else -> ""
    }
    val file = File(directory, "original$suffix")
    if (!file.isFile || file.length() != length) {
        directory.mkdirs()
        val temporary = Files.createTempFile(directory.toPath(), ".copy-", ".part").toFile()
        try {
            api.request(path).use { response ->
                missing(response)?.let { return@withContext it }
                if (!response.isSuccessful) throw IOException("original changed during download")
                val body = response.body ?: throw IOException("missing original")
                body.byteStream().use { input ->
                    temporary.outputStream().use { output ->
                        var copied = 0L
                        val buffer = ByteArray(64 * 1024)
                        while (true) {
                            val count = input.read(buffer)
                            if (count < 0) break
                            copied += count
                            if (copied > length) throw IOException("invalid original length")
                            output.write(buffer, 0, count)
                        }
                        if (copied != length) throw IOException("original download incomplete")
                        output.fd.sync()
                    }
                }
            }
            Files.move(temporary.toPath(), file.toPath(), ATOMIC_MOVE, REPLACE_EXISTING)
        } finally {
            temporary.delete()
        }
    }
    Original.Ready(file, name, type)
}
