package dev.niels.jarvis

import android.content.ActivityNotFoundException
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import android.os.Build
import android.os.RemoteException
import android.os.ext.SdkExtensions
import android.util.Size
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
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
import java.io.OutputStream
import kotlin.math.ceil
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONException
import org.json.JSONObject

private const val maxPreviewBytes = 100L * 1024 * 1024

class VerifiedFileProvider : FileProvider(R.xml.file_paths) {
    override fun onCreate(): Boolean {
        context?.cacheDir?.resolve("verified")?.deleteRecursively()
        return super.onCreate()
    }
}

private data class LocalPreview(val file: File, val mime: String)
private data class FileVisit(
    val item: JSONObject? = null, val local: LocalPreview? = null, val error: IOException? = null,
)

internal const val folderMime = "application/vnd.google-apps.folder"

internal fun originStatus(row: JSONObject): String = when (row.string("state")) {
    "filed" -> "open in files"
    "unavailable" -> if (row.string("disposition") == "deleted") "deleted" else "file unavailable"
    "uncertain" -> "local copy · drive may have received a file"
    "created" -> "only on jarvis · checking the drive copy"
    else -> "only on jarvis"
}

internal fun driveProblem(error: IOException): String = when ((error as? DriveFailure)?.code) {
    "drive_disconnected" -> "google drive isn’t connected."
    "drive_inaccessible" -> "this file is missing or you no longer have access."
    "drive_invalid_input" -> "this drive address is invalid."
    "drive_rate_limited" -> {
        val seconds = (error as? DriveFailure)?.retryAfter?.toLongOrNull()
        if (seconds == null) "google drive is limiting requests. try again shortly."
        else "google drive is limiting requests. retry in $seconds " + (if (seconds == 1L) "second." else "seconds.")
    }
    "drive_version_changed" -> "the file changed while opening. try again."
    "drive_cursor_stale" -> "this search expired. start it again."
    "drive_preview_too_large" -> "this file is too large to preview."
    "drive_preview_unsupported" -> "this file cannot be previewed here."
    else -> if (error is SignInRequired) "sign in to open your files." else "couldn’t check google drive."
}

@Composable
internal fun OriginPane(
    route: Route.File, api: HomeApi, reload: Pair<Int, Int>, signIn: () -> Unit,
    resolve: (Route) -> Unit,
) {
    var attempts by remember { mutableIntStateOf(0) }
    val checked by produceState<FileVisit?>(null, route, reload, attempts) {
        value = null
        value = try {
            FileVisit(item = api.drive("/api/drive/origin/${route.id}"))
        } catch (error: IOException) {
            FileVisit(error = error)
        }
    }
    val current = checked?.item
    Pane {
        val error = checked?.error
        when {
            error != null -> DriveRetry(error, signIn) { attempts++ }
            current == null -> CircularProgressIndicator()
            current.string("state") == "filed" -> {
                val canonical = Route.DriveFile(current.getString("subject"), current.getString("file_id"), route.page)
                LaunchedEffect(canonical) { resolve(canonical) }
            }
            else -> {
                val name = current.string("name") ?: "file"
                Heading(name)
                val received = current.string("received_at")?.let { " · received ${formattedTime(it)}" }.orEmpty()
                BodyStatus(originStatus(current) + received)
                if (current.string("state") != "unavailable") PendingDownload(api, route.id, name)
            }
        }
    }
}

@Composable
private fun PendingDownload(api: HomeApi, id: String, name: String) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var problem by remember { mutableStateOf<String?>(null) }
    var saving by remember { mutableStateOf(false) }
    val destination = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/octet-stream")) { uri ->
        if (uri != null) scope.launch {
            saving = true
            problem = null
            try {
                withContext(Dispatchers.IO) {
                    api.request("/api/drive/origin/$id/content").use { response ->
                        response.checkDrive()
                        val bytes = response.body ?: throw IOException("download unavailable")
                        val output = context.contentResolver.openOutputStream(uri) ?: throw IOException("destination unavailable")
                        output.use { bytes.writeExactly(it) }
                    }
                }
            } catch (_: IOException) {
                problem = "couldn’t save this upload."
            } finally {
                saving = false
            }
        }
    }
    TextButton(enabled = !saving, onClick = { destination.launch(name) }) { Text("download") }
    problem?.let { BodyStatus(it) }
}

@Composable
internal fun FilePane(
    route: Route.DriveFile, api: HomeApi, reload: Pair<Int, Int>, signIn: () -> Unit,
    navigate: (Route) -> Unit,
    attach: (DiscussionRef) -> Unit,
) {
    val context = LocalContext.current
    var attempt by remember { mutableIntStateOf(0) }
    val visit by produceState<FileVisit?>(null, route, reload, attempt) {
        value = null
        var path: File? = null
        try {
            val apiPath = "/api/drive/${route.subject}/${route.id}"
            val item = api.drive(apiPath)
            value = FileVisit(item = item)
            if (item.optBoolean("preview")) {
                val version = item.string("version") ?: throw IOException("file version unavailable")
                val file = withContext(Dispatchers.IO) {
                    val directory = context.cacheDir.resolve("verified")
                    directory.mkdirs()
                    File.createTempFile("drive-", ".preview", directory).also { path = it }
                }
                val mime = withContext(Dispatchers.IO) {
                    api.request("$apiPath/content?version=${Uri.encode(version)}").use { response ->
                        response.checkDrive()
                        val bytes = response.body ?: throw IOException("download unavailable")
                        val type = response.header("Content-Type")?.substringBefore(';')
                        if (type != item.getString("mime") || type !in previewTypes)
                            throw IOException("preview type changed")
                        file.outputStream().use { bytes.writeExactly(it) }
                        requireNotNull(type)
                    }
                }
                value = FileVisit(item = item, local = LocalPreview(file, mime))
                awaitCancellation()
            }
        } catch (error: IOException) {
            value = FileVisit(item = value?.item, error = error)
        } catch (_: JSONException) {
            value = FileVisit(error = IOException("invalid response"))
        } finally {
            path?.delete()
        }
    }
    val item = visit?.item
    if (item?.string("mime") == folderMime) {
        DriveList(item, api, reload, signIn, navigate, attach, route.subject)
    } else Pane {
        if (item != null) {
            Heading(item.getString("name"))
            FileActions(item, route) { attach(DiscussionRef.DriveFile(route.subject, route.id, null)) }
        }
        val current = visit
        val problem = current?.error
        when {
            problem != null -> DriveRetry(problem, signIn) { attempt++ }
            current == null -> CircularProgressIndicator()
            route.page != null && item?.string("mime") != "application/pdf" -> {
                BodyStatus("this file is no longer a pdf.")
                TextButton(onClick = { navigate(route.copy(page = null)) }) { Text("open the file") }
            }
            current.local != null -> FilePreview(current.local, route, attach)
            item?.optBoolean("preview") == true -> CircularProgressIndicator()
        }
    }
}

@Composable
private fun FileActions(item: JSONObject, route: Route.DriveFile, attach: () -> Unit) {
    val context = LocalContext.current
    var failed by remember { mutableStateOf(false) }
    FlowRow {
        TextButton(onClick = { failed = !openDrive(context, item.string("url")) }) { Text("open in drive") }
        TextButton(onClick = { copyLink(context, route.copy(page = null)) }) { Text("copy file link") }
        TextButton(onClick = attach) { Text("attach to chat") }
    }
    if (failed) BodyStatus("no browser or drive app is available.")
}

private fun openDrive(context: Context, url: String?): Boolean {
    val target = url?.let(Uri::parse) ?: return false
    if (target.scheme != "https" || target.encodedAuthority !in listOf("drive.google.com", "docs.google.com"))
        return false
    return try {
        context.startActivity(Intent(Intent.ACTION_VIEW, target))
        true
    } catch (_: ActivityNotFoundException) {
        false
    }
}

private fun copyLink(context: Context, route: Route.DriveFile) {
    context.getSystemService(ClipboardManager::class.java)
        .setPrimaryClip(ClipData.newPlainText("jarvis file link", Routes.url(route).toString()))
}

@Composable
private fun FilePreview(
    original: LocalPreview, route: Route.DriveFile, attach: (DiscussionRef) -> Unit,
) {
    val context = LocalContext.current
    var page by rememberSaveable(route.id, route.page) { mutableLongStateOf(route.page ?: 1L) }
    val pdf = original.mime == "application/pdf"
    val preview by produceState<Preview?>(null, original, page) {
        value = null
        value = previewOriginal(context, original, page)
    }
    val displayed = preview
    when {
        displayed == null -> CircularProgressIndicator()
        displayed.problem != null -> BodyStatus(displayed.problem)
        displayed.bitmap != null -> Image(
            displayed.bitmap.asImageBitmap(),
            if (pdf) "page $page of ${displayed.pages}" else "image preview",
            Modifier.fillMaxWidth(),
        )
    }
    if (pdf && displayed != null && displayed.pages > 0) {
        if (page > displayed.pages) {
            TextButton(onClick = { page = 1 }) { Text("open page 1") }
        } else if (displayed.pages > 1) {
            Text("page $page of ${displayed.pages}")
            FlowRow {
                TextButton(enabled = page > 1, onClick = { page-- }) { Text("previous page") }
                TextButton(enabled = page < displayed.pages, onClick = { page++ }) { Text("next page") }
                TextButton(onClick = { copyLink(context, route.copy(page = page)) }) { Text("copy page link") }
                TextButton(onClick = { attach(DiscussionRef.DriveFile(route.subject, route.id, page)) }) { Text("attach page to chat") }
            }
        }
    }
}

@Composable
internal fun DriveRetry(error: IOException, signIn: () -> Unit, retry: () -> Unit) {
    BodyStatus(driveProblem(error))
    when {
        error is SignInRequired -> TextButton(onClick = signIn) { Text("sign in") }
        error is DriveFailure && error.code == "drive_cursor_stale" -> TextButton(onClick = retry) { Text("restart search") }
        else -> TextButton(onClick = retry) { Text("retry") }
    }
}

private val previewTypes = setOf("application/pdf", "image/png", "image/jpeg", "image/gif", "image/webp")

private fun okhttp3.ResponseBody.writeExactly(output: OutputStream) {
    val length = contentLength()
    if (length !in 0..maxPreviewBytes) throw IOException("invalid file size")
    byteStream().use { input ->
        var copied = 0L
        val buffer = ByteArray(64 * 1024)
        while (true) {
            val count = input.read(buffer)
            if (count < 0) break
            copied += count
            if (copied > length) throw IOException("invalid file length")
            output.write(buffer, 0, count)
        }
        if (copied != length) throw IOException("file download incomplete")
    }
}

private data class Preview(val page: Long, val bitmap: Bitmap? = null, val pages: Int = 0, val problem: String? = null)

private suspend fun previewOriginal(context: Context, original: LocalPreview, number: Long): Preview =
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
                        return@withContext Preview(number, pages = count, problem = "page $number is unavailable in this file.")
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
