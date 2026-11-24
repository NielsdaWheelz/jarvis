package dev.niels.jarvis

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.OpenableColumns
import android.util.AtomicFile
import androidx.core.content.IntentCompat
import java.io.File
import java.io.FileNotFoundException
import java.io.IOException
import java.io.InputStream
import java.nio.file.Files
import java.nio.file.StandardCopyOption.ATOMIC_MOVE
import java.security.MessageDigest
import java.util.UUID
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
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

internal enum class DraftState { Editing, Frozen, Conflict, Received }

internal data class DraftFile(
    val slot: Int,
    val name: String,
    val size: Long,
    val sha256: String?,
    val problem: String?,
)

internal data class Draft(
    val id: String,
    val text: String = "",
    val ref: DiscussionRef? = null,
    val files: List<DraftFile> = emptyList(),
    val state: DraftState = DraftState.Editing,
    val receipt: String? = null,
)

internal enum class Transfer(val label: String) {
    Sending("sending"),
    Checking("checking receipt"),
    SignedOut("sign in, then send when ready"),
    Unconfirmed("send unconfirmed · retry this submission"),
    TooLarge("message or files are too large"),
    Invalid("check the message, files and reference"),
    Unavailable("could not send · saved on this phone");

    val active: Boolean get() = this == Sending || this == Checking
}

internal class Drafts private constructor(private val context: Context) {
    private val store = File(context.noBackupFilesDir, "drafts")
    private val process = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val changes = MutableStateFlow(0L)
    private val operations = MutableStateFlow<Map<String, Transfer>>(emptyMap())
    val revision = changes.asStateFlow()
    val transfers = operations.asStateFlow()

    init {
        store.listFiles()?.filter { it.name.startsWith(".incoming-") }?.forEach { it.deleteRecursively() }
    }

    suspend fun create(id: String, ref: DiscussionRef? = null): Draft = withContext(Dispatchers.IO) {
        synchronized(this@Drafts) { load(id) ?: Draft(id, ref = ref).also(::save) }
    }

    suspend fun receive(id: String, intent: Intent): Draft = withContext(Dispatchers.IO) {
        load(id)?.let { return@withContext it }
        val share = when (intent.action) {
            Intent.ACTION_SEND, Intent.ACTION_SEND_MULTIPLE -> intent.sharedStreams()
            Intent.ACTION_PROCESS_TEXT -> emptyList()
            else -> throw IOException("this share is unavailable")
        }
        val sharedText = when (intent.action) {
            Intent.ACTION_PROCESS_TEXT -> intent.getCharSequenceExtra(Intent.EXTRA_PROCESS_TEXT)
            else -> intent.getCharSequenceExtra(Intent.EXTRA_TEXT) ?: intent.clipData?.let { clip ->
                List(clip.itemCount) { clip.getItemAt(it).text }.filterNotNull().joinToString("\n")
            }
        }?.takeUnless { it.isEmpty() }
        val count = share.size + if (sharedText != null) 1 else 0
        if (count == 0) throw IOException("this share is empty")

        store.mkdirs()
        val staging = Files.createTempDirectory(store.toPath(), ".incoming-").toFile()
        try {
            val copied = mutableListOf<DraftFile>()
            var remaining = BodyLimit
            for (index in 0 until minOf(count, FileLimit)) {
                val uri = share.getOrNull(index)
                val name = if (index == share.size) "shared text.txt" else fileName(uri, index)
                val stored = File(staging, "file-$index")
                val result = try {
                    val input = if (index == share.size) {
                        requireNotNull(sharedText).toString().toByteArray(Charsets.UTF_8).inputStream()
                    } else if (uri?.scheme == "content") {
                        context.contentResolver.openInputStream(uri) ?: throw FileNotFoundException()
                    } else {
                        throw FileNotFoundException()
                    }
                    input.use { copyOriginal(it, stored, index, name, remaining) }
                } catch (e: IOException) {
                    stored.delete()
                    DraftFile(index, name, 0, null, e.message.takeIf { e is ShareTooLarge } ?: "could not copy · re-share or remove")
                } catch (e: SecurityException) {
                    stored.delete()
                    DraftFile(index, name, 0, null, "could not read · re-share or remove")
                } catch (e: RuntimeException) {
                    if (e is kotlinx.coroutines.CancellationException) throw e
                    stored.delete()
                    DraftFile(index, name, 0, null, "could not read · re-share or remove")
                }
                copied.add(result)
                remaining -= result.size
            }
            if (count > FileLimit) {
                copied.add(DraftFile(FileLimit, "${count - FileLimit} additional items", 0, null, "at most ten files · re-share or remove"))
            }
            val draft = Draft(id, files = copied)
            write(staging, draft)
            Files.move(staging.toPath(), directory(id).toPath(), ATOMIC_MOVE)
            changes.update { it + 1 }
            draft
        } finally {
            staging.deleteRecursively()
        }
    }

    suspend fun get(id: String): Draft? = withContext(Dispatchers.IO) { load(id) }

    suspend fun list(): List<Draft> = withContext(Dispatchers.IO) {
        synchronized(this@Drafts) {
            store.listFiles().orEmpty().asSequence()
                .filterNot { it.name.startsWith(".") }
                .sortedByDescending { File(it, "draft.json").lastModified() }
                .mapNotNull { load(it.name) }
                .toList()
        }
    }

    suspend fun edit(id: String, text: String, removeSlot: Int? = null, detach: Boolean = false) {
        withContext(Dispatchers.IO) {
            synchronized(this@Drafts) {
                val original = load(id) ?: return@synchronized
                if (original.state != DraftState.Editing) return@synchronized
                val edited = original.copy(
                    text = text,
                    ref = if (detach) null else original.ref,
                    files = original.files.filterNot { it.slot == removeSlot },
                )
                if (edited != original) {
                    save(edited)
                    operations.update {
                        if (it[id] == Transfer.TooLarge || it[id] == Transfer.Invalid) it - id else it
                    }
                    removeSlot?.let { File(directory(id), "file-$it").delete() }
                }
            }
        }
    }

    suspend fun discard(id: String): Boolean = withContext(Dispatchers.IO) {
        synchronized(this@Drafts) {
            if (operations.value[id]?.active == true) return@synchronized false
            if (directory(id).exists() && !directory(id).deleteRecursively()) return@synchronized false
            operations.update { it - id }
            changes.update { it + 1 }
            true
        }
    }

    fun send(id: String, text: String, api: HomeApi) = operation(id, Transfer.Sending) {
        if (Access.get(context).currentBearer() == null) throw SignInRequired()
        val (body, firstAttempt) = synchronized(this) {
            val draft = load(id) ?: return@operation Transfer.Unavailable
            if (draft.state != DraftState.Editing && draft.state != DraftState.Frozen) return@operation null
            val firstAttempt = draft.state == DraftState.Editing
            val frozen = if (firstAttempt) draft.copy(text = text) else draft
            if ('\u0000' in frozen.text || (frozen.text.isBlank() && frozen.files.isEmpty()) || frozen.files.any { it.problem != null }) {
                return@operation Transfer.Invalid
            }
            if (frozen.text.toByteArray(Charsets.UTF_8).size > TextLimit) return@operation Transfer.TooLarge
            val encoded = encode(frozen)
            if (encoded.contentLength() > BodyLimit) return@operation Transfer.TooLarge
            save(frozen.copy(state = DraftState.Frozen))
            encoded to firstAttempt
        }
        api.request("/api/messages/$id", "PUT", body).use { response ->
            when (response.code) {
                200, 201 -> accepted(id, response.json())
                409 -> {
                    synchronized(this) { save(checkNotNull(load(id)).copy(state = DraftState.Conflict)) }
                    null
                }
                413, 422 -> {
                    // Rejection establishes this attempt's outcome. An earlier uncertain attempt can still commit.
                    if (firstAttempt) synchronized(this) {
                        save(checkNotNull(load(id)).copy(state = DraftState.Editing))
                    }
                    if (response.code == 413) Transfer.TooLarge else Transfer.Invalid
                }
                else -> Transfer.Unconfirmed
            }
        }
    }

    fun signedIn(id: String) {
        operations.update { if (it[id] == Transfer.SignedOut) it - id else it }
    }

    fun checkReceipt(id: String, api: HomeApi) = operation(id, Transfer.Checking) {
        if (load(id)?.state != DraftState.Frozen) return@operation null
        val receipt = api.read("/api/submissions/$id") ?: return@operation Transfer.Unconfirmed
        accepted(id, receipt)
    }

    @Synchronized
    private fun operation(id: String, transfer: Transfer, run: suspend () -> Transfer?) {
        if (operations.value[id]?.active == true) return
        operations.update { it + (id to transfer) }
        process.launch {
            val final = try {
                run()
            } catch (_: SignInRequired) {
                Transfer.SignedOut
            } catch (_: IOException) {
                val state = try { load(id)?.state } catch (_: IOException) { null }
                if (state == DraftState.Frozen) Transfer.Unconfirmed else Transfer.Unavailable
            }
            operations.update { if (final == null) it - id else it + (id to final) }
        }
    }

    @Synchronized
    private fun accepted(id: String, response: JSONObject): Transfer? {
        val receipt = response.string("id")?.takeIf { canonicalUuid(it) } ?: return Transfer.Unconfirmed
        val draft = checkNotNull(load(id))
        if (draft.state == DraftState.Frozen) {
            save(draft.copy(state = DraftState.Received, receipt = receipt))
        }
        return null
    }

    private fun encode(draft: Draft): RequestBody {
        val json = JSONObject().put("text", draft.text).put("ref", draft.ref?.json() ?: JSONObject.NULL)
        if (draft.files.isEmpty()) return json.toString().toRequestBody(Json)
        return MultipartBody.Builder().setType(MultipartBody.FORM)
            .addFormDataPart("message", json.toString()).apply {
                for (file in draft.files) {
                    addFormDataPart("file", file.name, File(directory(draft.id), "file-${file.slot}").asRequestBody(Octets))
                }
            }.build()
    }

    private fun directory(id: String) = File(store, id)

    @Synchronized
    private fun load(id: String): Draft? {
        val manifest = AtomicFile(File(directory(id), "draft.json"))
        return try {
            val data = JSONObject(manifest.readFully().decodeToString())
            Draft(
                id = id,
                text = data.getString("text"),
                ref = DiscussionRef.parse(data.optJSONObject("ref")),
                files = data.objects("files").map {
                    DraftFile(it.getInt("slot"), it.getString("name"), it.getLong("size"), it.string("sha256"), it.string("problem"))
                },
                state = DraftState.valueOf(data.getString("state")),
                receipt = data.string("receipt"),
            )
        } catch (_: FileNotFoundException) {
            null
        } catch (e: JSONException) {
            throw IOException("could not read this draft", e)
        }
    }

    private fun save(draft: Draft) {
        write(directory(draft.id), draft)
        changes.update { it + 1 }
    }

    private fun write(directory: File, draft: Draft) {
        val data = JSONObject().put("text", draft.text).put("ref", draft.ref?.json())
            .put("state", draft.state.name).put("receipt", draft.receipt)
            .put("files", JSONArray().also { files ->
                for (file in draft.files) {
                    files.put(JSONObject().put("slot", file.slot).put("name", file.name)
                        .put("size", file.size).put("sha256", file.sha256).put("problem", file.problem))
                }
            })
        val manifest = AtomicFile(File(directory, "draft.json"))
        val stream = manifest.startWrite()
        try {
            stream.write(data.toString().toByteArray(Charsets.UTF_8))
            manifest.finishWrite(stream)
        } catch (e: IOException) {
            manifest.failWrite(stream)
            throw e
        }
    }

    private fun Intent.sharedStreams(): List<Uri?> = when {
        !hasExtra(Intent.EXTRA_STREAM) -> clipData?.let { clip ->
            List(clip.itemCount) { clip.getItemAt(it).uri }.filterNotNull()
        }.orEmpty()
        action == Intent.ACTION_SEND_MULTIPLE -> IntentCompat.getParcelableArrayListExtra(this, Intent.EXTRA_STREAM, Uri::class.java)
            ?: listOf(null)
        else -> listOf(IntentCompat.getParcelableExtra(this, Intent.EXTRA_STREAM, Uri::class.java))
    }

    private fun fileName(uri: Uri?, slot: Int): String {
        val name = if (uri?.scheme != "content") null else try {
            context.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)
                ?.use { if (it.moveToFirst()) it.getString(0) else null }
        } catch (_: SecurityException) {
            null
        } catch (e: RuntimeException) {
            if (e is kotlinx.coroutines.CancellationException) throw e
            null
        }
        return displayFileName(name, "file ${slot + 1}")
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

private class ShareTooLarge : IOException("upload exceeds 90 mib · re-share or remove")

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
    return DraftFile(slot, name, size, digest.digest().joinToString("") { "%02x".format(it) }, null)
}
