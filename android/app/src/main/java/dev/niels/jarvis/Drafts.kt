package dev.niels.jarvis

import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.ImageDecoder
import android.net.Uri
import android.os.Bundle
import android.os.SystemClock
import android.provider.OpenableColumns
import android.util.AtomicFile
import android.webkit.MimeTypeMap
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshots.Snapshot
import androidx.core.content.IntentCompat
import java.io.File
import java.io.FileNotFoundException
import java.io.IOException
import java.io.InputStream
import java.lang.ref.Reference
import java.nio.file.Files
import java.nio.file.StandardCopyOption.ATOMIC_MOVE
import java.security.MessageDigest
import java.util.UUID
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.RequestBody
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONException
import org.json.JSONObject

private const val FileLimit = 10
private const val BodyLimit = 90L * 1024 * 1024
internal const val TextLimit = 16 * 1024
private val Json = "application/json".toMediaType()
private val Octets = "application/octet-stream".toMediaType()
internal const val SettleEarlier = "settle the earlier message first."
internal const val ReceiptUnknown = "no receipt yet. retry is safe: it cannot arrive twice."
internal enum class ReceiptCheck { Checking, Unavailable, Missing }

internal data class DraftFile(
    val slot: Int,
    val name: String,
    val size: Long,
    val sha256: String?,
    val problem: String? = null,
)

internal data class Draft(
    val id: String = UUID.randomUUID().toString(),
    val text: String = "",
    val ref: DiscussionRef? = null,
    val files: List<DraftFile> = emptyList(),
    val held: Boolean = false,
) {
    fun canSend(words: String) = (words.isNotBlank() || files.isNotEmpty()) &&
        '\u0000' !in words && words.toByteArray(Charsets.UTF_8).size <= TextLimit &&
        files.none { it.problem != null }
}

internal class Drafts private constructor(private val context: Context) {
    private val store = File(context.noBackupFilesDir, "draft")
    private val manifest = AtomicFile(File(store, "draft.json"))
    private val process = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private val writes = Mutex()
    private val receipts = Mutex()
    private var transferJob: Job? = null

    var draft by mutableStateOf<Draft?>(null)
        private set
    var sendingSince by mutableStateOf<Long?>(null)
        private set
    var copying by mutableIntStateOf(0)
        private set
    var receiptCheck by mutableStateOf(ReceiptCheck.Checking)
        private set
    var problem by mutableStateOf<String?>(null)
        private set
    val sending get() = sendingSince != null
    val locked get() = sending || draft?.held == true

    private val ready = process.launch {
        try {
            draft = withContext(Dispatchers.IO) {
                val existing = load() ?: Draft()
                reclaim(existing)
                existing
            }
        } catch (_: IOException) {
            problem = "could not read the draft on this phone"
        }
    }

    fun edit(id: String, text: String) {
        process.launch {
            writes.withLock {
                val current = draft ?: return@withLock
                if (current.id != id || locked || current.text == text) return@withLock
                try {
                    save(current.copy(text = text))
                    problem = null
                } catch (_: IOException) {
                    problem = "could not save these words"
                }
            }
        }
    }

    fun reference(ref: DiscussionRef?) {
        process.launch {
            ready.join()
            writes.withLock {
                val current = draft ?: return@withLock
                if (locked || current.ref == ref) return@withLock
                try {
                    save(current.copy(ref = ref))
                    problem = null
                } catch (_: IOException) {
                    problem = "could not save this reference"
                }
            }
        }
    }

    fun append(uris: List<Uri>, imeExtras: Bundle? = null) {
        if (locked || uris.isEmpty()) return
        copying++
        process.launch {
            try {
                addOriginals(uris, null, fromShare = false)
            } catch (e: DraftProblem) {
                problem = e.message
            } catch (_: IOException) {
                problem = "could not save these files. check free space and try again."
            } finally {
                // Compose owns this temporary read grant until the copy finishes.
                Reference.reachabilityFence(imeExtras)
                copying--
            }
        }
    }

    suspend fun receive(intent: Intent) {
        ready.join()
        if (locked) throw DraftProblem(SettleEarlier)
        val streams = when (intent.action) {
            Intent.ACTION_SEND, Intent.ACTION_SEND_MULTIPLE -> intent.sharedStreams()
            Intent.ACTION_PROCESS_TEXT -> emptyList()
            else -> throw DraftProblem("this share is unavailable")
        }
        val text = when (intent.action) {
            Intent.ACTION_PROCESS_TEXT -> intent.getCharSequenceExtra(Intent.EXTRA_PROCESS_TEXT)
            else -> intent.getCharSequenceExtra(Intent.EXTRA_TEXT) ?: intent.clipData?.let { clip ->
                List(clip.itemCount) { clip.getItemAt(it).text }.filterNotNull().joinToString("\n")
            }
        }?.toString()?.takeIf(String::isNotEmpty)
        if (streams.isEmpty() && text == null) throw DraftProblem("this share is empty")
        copying++
        try {
            addOriginals(streams, text, fromShare = true)
        } finally {
            copying--
        }
    }

    private suspend fun addOriginals(uris: List<Uri?>, text: String?, fromShare: Boolean) = writes.withLock {
        val current = draft ?: throw DraftProblem("could not open the draft on this phone")
        if (locked) throw DraftProblem(SettleEarlier)
        val count = uris.size + if (text != null) 1 else 0
        if (count > FileLimit - current.files.size) throw DraftProblem("at most ten files. remove a file first.")
        val staging = withContext(NonCancellable) {
            withContext(Dispatchers.IO) {
                store.mkdirs()
                Files.createTempDirectory(store.toPath(), ".incoming-").toFile()
            }
        }
        try {
            val added = withContext(Dispatchers.IO) {
                var remaining = BodyLimit - current.files.sumOf(DraftFile::size)
                val firstSlot = (current.files.maxOfOrNull(DraftFile::slot) ?: -1) + 1
                List(count) { index ->
                    val slot = firstSlot + index
                    val uri = uris.getOrNull(index)
                    val isText = index == uris.size
                    val name = if (isText) "shared text.txt" else fileName(uri, slot, fromShare)
                    val target = staging.resolve("file-$slot")
                    val original = try {
                        val input = when {
                            isText -> checkNotNull(text).toByteArray(Charsets.UTF_8).inputStream()
                            uri?.scheme == "content" -> context.contentResolver.openInputStream(uri) ?: throw FileNotFoundException()
                            else -> throw FileNotFoundException()
                        }
                        input.use { copyOriginal(it, target, slot, name, remaining) }
                    } catch (_: ShareTooLarge) {
                        throw DraftProblem("message and files exceed 90 mib")
                    } catch (e: Exception) {
                        if (e is CancellationException) throw e
                        target.delete()
                        if (!fromShare) throw DraftProblem("could not copy $name. add it again.")
                        DraftFile(slot, name, 0, null, "could not copy. re-share or remove.")
                    }
                    remaining -= original.size
                    original
                }
            }
            withContext(NonCancellable) {
                val result = current.copy(files = current.files + added)
                withContext(Dispatchers.IO) {
                    try {
                        for (file in added.filter { it.sha256 != null }) {
                            val name = "file-${file.slot}"
                            Files.move(staging.resolve(name).toPath(), store.resolve(name).toPath(), ATOMIC_MOVE)
                        }
                        if (added.all { it.problem == null } && encode(result).contentLength() > BodyLimit) {
                            throw DraftProblem("message and files exceed 90 mib")
                        }
                        write(result)
                    } catch (e: IOException) {
                        // The recovered manifest owns private bytes even after a write error.
                        reclaim(load() ?: current)
                        throw e
                    }
                }
                draft = result
                problem = null
            }
        } finally {
            withContext(NonCancellable + Dispatchers.IO) { staging.deleteRecursively() }
        }
    }

    fun remove(slot: Int) {
        if (locked || copying > 0) return
        process.launch {
            writes.withLock {
                val current = draft ?: return@withLock
                if (locked) return@withLock
                try {
                    save(current.copy(files = current.files.filterNot { it.slot == slot }), removeOld = true)
                    problem = null
                } catch (_: IOException) {
                    problem = "could not remove this file"
                }
            }
        }
    }

    suspend fun thumbnail(slot: Int): Bitmap? = withContext(Dispatchers.IO) {
        try {
            ImageDecoder.decodeBitmap(ImageDecoder.createSource(store.resolve("file-$slot"))) { decoder, info, _ ->
                val largest = maxOf(info.size.width, info.size.height)
                if (largest > 144) decoder.setTargetSampleSize((largest + 143) / 144)
            }
        } catch (_: IOException) {
            null
        }
    }

    fun send(words: String, api: HomeApi, history: ChatHistory): Boolean {
        val initial = draft ?: return false
        if (sending || (initial.held && receiptCheck != ReceiptCheck.Missing) || copying > 0 ||
            !initial.canSend(if (initial.held) initial.text else words)
        ) return false
        sendingSince = SystemClock.elapsedRealtime()
        receiptCheck = ReceiptCheck.Checking
        problem = null
        val epoch = history.authorizationEpoch
        transferJob = process.launch(start = CoroutineStart.LAZY) {
            val attempt = coroutineContext[Job]
            try {
                val frozen = writes.withLock {
                    val current = checkNotNull(draft)
                    val updated = if (current.held) current else current.copy(text = words, held = true)
                    val body = encode(updated)
                    if (body.contentLength() > BodyLimit) {
                        if (!current.held && current.text != words) save(current.copy(text = words))
                        problem = "message or files are too large."
                        return@launch
                    }
                    if (current != updated) save(updated)
                    body
                }
                api.submit(initial.id, frozen).let { (code, receipt) ->
                    writes.withLock {
                        if (transferJob !== attempt) return@withLock
                        val current = checkNotNull(draft)
                        when (code) {
                            200, 201 -> cross(checkNotNull(receipt), history, epoch)
                            409 -> {
                                save(current.copy(id = UUID.randomUUID().toString(), held = false))
                                problem = "a different message already used this send. it is in the conversation."
                            }
                            400, 413, 422, 426 -> {
                                if (!initial.held) save(current.copy(held = false))
                                problem = when (code) {
                                    400 -> "use the private home address to send."
                                    413 -> "message or files are too large."
                                    426 -> UpdateViewerMessage
                                    else -> "check the message, files and reference."
                                }
                            }
                        }
                    }
                }
            } catch (lost: SignInRequired) {
                if (transferJob === attempt) {
                    problem = "sign in to check whether your message arrived"
                    history.rejectAccess(lost)
                }
            } catch (_: IOException) {
                if (transferJob === attempt && draft?.held != true) problem = "could not save these words"
            } finally {
                if (transferJob === attempt) {
                    sendingSince = null
                    transferJob = null
                }
            }
        }
        transferJob?.start()
        return true
    }

    fun stopWaiting() {
        val job = transferJob ?: return
        if (draft?.held == true) {
            transferJob = null
            sendingSince = null
        }
        job.cancel()
    }

    // A page taken before this ordered lookup can have no row for a 404.
    // An active PUT must settle first, because its 409 can name someone else's row.
    suspend fun checkReceipt(api: HomeApi, history: ChatHistory): Boolean = receipts.withLock {
        ready.join()
        val waiting = draft?.takeIf(Draft::held)
        if (sending || draft == null) return false
        if (waiting == null) return true
        val epoch = history.authorizationEpoch
        val receipt = try {
            api.receipt(waiting.id)
        } catch (e: IOException) {
            if (draft?.id == waiting.id && !sending) receiptCheck = ReceiptCheck.Unavailable
            throw e
        }
        writes.withLock {
            if (sending || epoch != history.authorizationEpoch) return false
            if (draft?.id != waiting.id) return draft?.held == false
            if (receipt != null) cross(receipt, history, epoch)
            else {
                receiptCheck = ReceiptCheck.Missing
                true
            }
        }
    }

    fun discard() {
        if (sending || copying > 0 || draft?.held != true) return
        process.launch {
            writes.withLock {
                if (sending || draft?.held != true) return@withLock
                try {
                    save(Draft(), removeOld = true)
                    problem = null
                } catch (_: IOException) {
                    problem = "could not discard these words"
                }
            }
        }
    }

    private suspend fun cross(receipt: SubmissionReceipt, history: ChatHistory, epoch: Int) =
        history.admitReceipt(epoch) {
            withContext(NonCancellable) {
                val reset = Draft()
                withContext(Dispatchers.IO) {
                    write(reset)
                    reclaim(reset)
                }
                Snapshot.withMutableSnapshot {
                    draft = reset
                    problem = null
                    sendingSince = null
                    history.accept(receipt.message)
                }
                history.notifyReceipt()
            }
        }

    private suspend fun save(value: Draft, removeOld: Boolean = false) = withContext(NonCancellable) {
        withContext(Dispatchers.IO) {
            write(value)
            if (removeOld) reclaim(value)
        }
        draft = value
    }

    private fun reclaim(draft: Draft) {
        val retained = draft.files.mapTo(mutableSetOf()) { "file-${it.slot}" }
        store.listFiles()?.forEach {
            if (it.name.startsWith(".incoming-")) it.deleteRecursively()
            else if (it.name.startsWith("file-") && it.name !in retained) it.delete()
        }
    }

    private fun encode(draft: Draft): RequestBody {
        val json = JSONObject().put("text", draft.text).put("ref", draft.ref?.json() ?: JSONObject.NULL)
        if (draft.files.isEmpty()) return json.toString().toRequestBody(Json)
        return MultipartBody.Builder().setType(MultipartBody.FORM)
            .addFormDataPart("message", json.toString()).apply {
                for (file in draft.files) {
                    addFormDataPart("file", file.name, store.resolve("file-${file.slot}").asRequestBody(Octets))
                }
            }.build()
    }

    private fun load(): Draft? = try {
        val data = JSONObject(manifest.readFully().decodeToString())
        Draft(
            id = data.getString("id"),
            text = data.getString("text"),
            ref = DiscussionRef.parse(data.optJSONObject("ref")),
            files = data.objects("files").map {
                DraftFile(it.getInt("slot"), it.getString("name"), it.getLong("size"), it.string("sha256"), it.string("problem"))
            },
            held = data.getBoolean("held"),
        )
    } catch (_: FileNotFoundException) {
        null
    } catch (e: JSONException) {
        throw IOException("could not read this draft", e)
    }

    private fun write(draft: Draft) {
        val data = JSONObject().put("id", draft.id).put("text", draft.text).put("ref", draft.ref?.json())
            .put("held", draft.held).put("files", JSONArray().also { files ->
                for (file in draft.files) {
                    files.put(JSONObject().put("slot", file.slot).put("name", file.name)
                        .put("size", file.size).put("sha256", file.sha256).put("problem", file.problem))
                }
            })
        val bytes = data.toString().toByteArray(Charsets.UTF_8)
        val stream = manifest.startWrite()
        try {
            stream.write(bytes)
            stream.fd.sync()
            manifest.finishWrite(stream)
        } catch (e: IOException) {
            manifest.failWrite(stream)
            throw e
        }
        // AtomicFile logs rename failures; acknowledge only the recovered bytes.
        if (!manifest.readFully().contentEquals(bytes)) throw IOException("could not save this draft")
    }

    private fun Intent.sharedStreams(): List<Uri?> = when {
        !hasExtra(Intent.EXTRA_STREAM) -> clipData?.let { clip ->
            List(clip.itemCount) { clip.getItemAt(it).uri }.filterNotNull()
        }.orEmpty()
        action == Intent.ACTION_SEND_MULTIPLE -> IntentCompat.getParcelableArrayListExtra(this, Intent.EXTRA_STREAM, Uri::class.java)
            ?: listOf(null)
        else -> listOf(IntentCompat.getParcelableExtra(this, Intent.EXTRA_STREAM, Uri::class.java))
    }

    private fun fileName(uri: Uri?, slot: Int, fromShare: Boolean): String {
        val fallback = "file ${slot + 1}"
        if (uri?.scheme != "content") return fallback
        return try {
            val type = context.contentResolver.getType(uri)
            val ext = MimeTypeMap.getSingleton().getExtensionFromMimeType(type)
            val unnamed = if (!fromShare && type?.startsWith("image/") == true && ext != null) "pasted image.$ext" else fallback
            val name = context.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)
                ?.use { if (it.moveToFirst()) it.getString(0) else null }
            displayFileName(name, unnamed)
        } catch (_: SecurityException) {
            fallback
        } catch (e: RuntimeException) {
            if (e is CancellationException) throw e
            fallback
        }
    }

    companion object {
        @Volatile private var instance: Drafts? = null

        fun get(context: Context): Drafts = instance ?: synchronized(this) {
            instance ?: Drafts(context.applicationContext).also { instance = it }
        }
    }
}

internal fun displayFileName(name: String?, fallback: String): String =
    name?.substringAfterLast('/')?.substringAfterLast('\\')?.filterNot { it.isISOControl() }
        ?.trim()?.takeUnless { it.isBlank() || it == "." || it == ".." } ?: fallback

internal fun canonicalUuid(value: String): Boolean = try {
    UUID.fromString(value).toString() == value
} catch (_: IllegalArgumentException) {
    false
}

internal class DraftProblem(message: String) : IOException(message)
private class ShareTooLarge : IOException()

private fun copyOriginal(input: InputStream, target: File, slot: Int, name: String, limit: Long): DraftFile {
    val digest = MessageDigest.getInstance("SHA-256")
    var size = 0L
    target.outputStream().use { output ->
        val buffer = ByteArray(64 * 1024)
        while (true) {
            val count = input.read(buffer)
            if (count < 0) break
            size += count
            if (size > limit) throw ShareTooLarge()
            digest.update(buffer, 0, count)
            output.write(buffer, 0, count)
        }
        output.fd.sync()
    }
    return DraftFile(slot, name, size, digest.digest().joinToString("") { "%02x".format(it) })
}
