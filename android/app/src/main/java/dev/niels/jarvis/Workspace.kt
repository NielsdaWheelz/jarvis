package dev.niels.jarvis

import android.content.Intent
import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.window.DialogProperties
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.repeatOnLifecycle
import java.io.IOException
import java.nio.ByteBuffer
import java.security.MessageDigest
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.UUID
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONException
import org.json.JSONObject

private const val approvals = "/api/workspace/approvals"
private val jsonMedia = "application/json".toMediaType()

internal data class WorkspaceApproval(
    val id: String,
    val product: String,
    val operation: String,
    val prompt: String,
    val choices: List<Pair<String, String>>,
    val expires: Instant,
)

private suspend fun HomeApi.pendingApproval(): WorkspaceApproval? = withContext(Dispatchers.IO) {
    request(approvals).use { response ->
        if (!response.isSuccessful) throw IOException("google approval status unavailable")
        val list = JSONArray(response.body?.string() ?: throw IOException("empty approval response"))
        if (list.length() == 0) return@withContext null
        if (list.length() != 1) throw IOException("unexpected approval count")
        val item = list.getJSONObject(0)
        val id = item.getString("id").takeIf(::canonicalUuid) ?: throw IOException("invalid approval id")
        val choices = item.getJSONArray("choices").objects().map {
            it.getString("value") to it.getString("label")
        }
        val expires = Instant.parse(item.getString("expires_at"))
        if (choices.isEmpty() || !expires.isAfter(Instant.now())) return@withContext null
        WorkspaceApproval(id, item.getString("product"), item.getString("operation"),
            item.getString("prompt"), choices, expires)
    }
}

@Composable
internal fun WorkspaceApprovalPanel(api: HomeApi, authRevision: Int) {
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    val scope = rememberCoroutineScope()
    var current by remember(authRevision) { mutableStateOf<WorkspaceApproval?>(null) }
    var submitted by remember(authRevision) { mutableStateOf<String?>(null) }
    var status by remember(authRevision) { mutableStateOf<String?>(null) }
    LaunchedEffect(lifecycle, api, authRevision) {
        lifecycle.repeatOnLifecycle(Lifecycle.State.RESUMED) {
            try {
                while (true) {
                    current = try {
                        api.pendingApproval()
                    } catch (_: IOException) {
                        null
                    } catch (_: JSONException) {
                        null
                    } catch (_: java.time.DateTimeException) {
                        null
                    }
                    delay(1500)
                }
            } finally {
                current = null
            }
        }
    }
    val form = current?.takeIf { it.id != submitted }
    if (form == null) {
        status?.let { Text(it) }
        return
    }
    fun respond(choice: String?) {
        if (submitted == form.id || current?.id != form.id) return
        submitted = form.id
        if (!form.expires.isAfter(Instant.now())) {
            status = "google’s question expired"
            return
        }
        status = "recording your choice…"
        scope.launch {
            val body = JSONObject().put("choice", choice ?: JSONObject.NULL).toString().toRequestBody(jsonMedia)
            status = try {
                api.request("$approvals/${form.id}", "POST", body).use { response ->
                    when (response.code) {
                        204 -> if (choice == null) "cancellation recorded" else "choice recorded"
                        409 -> "this question was already answered or replaced"
                        410 -> "google’s question expired"
                        else -> "your choice is unconfirmed"
                    }
                }
            } catch (_: IOException) {
                "your choice is unconfirmed"
            }
        }
    }
    WorkspaceApprovalDialog(form, ::respond)
}

@Composable
internal fun WorkspaceApprovalDialog(form: WorkspaceApproval, respond: (String?) -> Unit) {
    val local = DateTimeFormatter.ofPattern("HH:mm:ss z").withZone(ZoneId.systemDefault()).format(form.expires)
    AlertDialog(
        onDismissRequest = { respond(null) },
        properties = DialogProperties(dismissOnClickOutside = false),
        title = { Text("google needs your choice") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                Text("${form.product} · ${form.operation}")
                Text(form.prompt)
                Text("expires at $local")
                form.choices.forEach { (value, label) ->
                    TextButton(onClick = { respond(value) }) { Text(label) }
                }
            }
        },
        confirmButton = { TextButton(onClick = { respond(null) }) { Text("cancel request") } },
    )
}

internal fun workspaceRefreshId(occurrence: UUID): UUID {
    val bytes = MessageDigest.getInstance("SHA-1").apply {
        update(ByteBuffer.allocate(16).putLong(occurrence.mostSignificantBits)
            .putLong(occurrence.leastSignificantBits).array())
        update("refresh".toByteArray(Charsets.UTF_8))
    }.digest()
    bytes[6] = ((bytes[6].toInt() and 0x0f) or 0x50).toByte()
    bytes[8] = ((bytes[8].toInt() and 0x3f) or 0x80).toByte()
    return ByteBuffer.wrap(bytes).let { UUID(it.long, it.long) }
}

/** Only the immutable pending intent for this occurrence may start a fresh read. */
internal class WorkspaceTapActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val uri = intent.data
        val parts = uri?.pathSegments.orEmpty()
        if (uri?.scheme != "jarvis-check" || uri.authority != "tap" || parts.size != 2 ||
            !parts.all(::canonicalUuid)) {
            finish()
            return
        }
        val (occurrence, todo) = parts
        val submission = workspaceRefreshId(UUID.fromString(occurrence))
        val api = HomeApi(this)
        val access = Access.get(this)
        fun open(route: Route) {
            startActivity(Intent(Intent.ACTION_VIEW, Routes.url(route), this, MainActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP))
            finish()
        }
        setContent {
            val auth by access.revision.collectAsState()
            var attempt by rememberSaveable { mutableIntStateOf(0) }
            var status by remember { mutableStateOf("requesting a fresh check…") }
            var retry by remember { mutableStateOf(false) }
            var signedOut by remember { mutableStateOf(false) }
            LaunchedEffect(attempt, auth) {
                retry = false
                signedOut = false
                val body = JSONObject().put("text", "check this workspace condition again.")
                    .put("ref", DiscussionRef.Todo(todo).json()).toString().toRequestBody(jsonMedia)
                try {
                    api.request("/api/messages/$submission", "PUT", body,
                        headers = mapOf("X-Jarvis-Workspace-Occurrence" to occurrence)).use { response ->
                        when (response.code) {
                            200, 201 -> {
                                val id = withContext(Dispatchers.IO) { response.json().getString("id") }
                                if (!canonicalUuid(id)) throw IOException("invalid receipt")
                                Toast.makeText(this@WorkspaceTapActivity, "fresh check requested", Toast.LENGTH_SHORT).show()
                                open(Route.Todo(todo))
                            }
                            409, 410, 422 -> status = "this check has changed or is no longer available"
                            else -> throw IOException("unconfirmed")
                        }
                    }
                } catch (_: SignInRequired) {
                    signedOut = true
                    status = "sign in to request fresh details"
                } catch (_: IOException) {
                    retry = true
                    status = "fresh check unconfirmed"
                } catch (_: JSONException) {
                    retry = true
                    status = "fresh check unconfirmed"
                }
            }
            JarvisPaper {
                Pane {
                    Text(status)
                    if (signedOut) TextButton(onClick = { access.signIn(this@WorkspaceTapActivity) }) { Text("sign in") }
                    if (retry) TextButton(onClick = { attempt++ }) { Text("retry this request") }
                    TextButton(onClick = { open(Route.Todo(todo)) }) { Text("open todo and earlier results") }
                }
            }
        }
    }
}
