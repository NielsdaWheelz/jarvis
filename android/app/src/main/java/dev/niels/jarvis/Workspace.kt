package dev.niels.jarvis

import android.content.Intent
import android.os.Bundle
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
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.Modifier
import androidx.compose.ui.window.DialogProperties
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.repeatOnLifecycle
import java.io.IOException
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

@Composable
internal fun WorkspaceBlockEntry(block: JSONObject) {
    val id = block.getString("id")
    val revision = block.getLong("revision")
    val product = block.getString("product")
    val operation = block.getString("operation").replace('_', ' ')
    val state = block.getString("state")
    val reason = block.getString("reason")
    val remedy = block.getString("remedy")
    val retryAt = if (block.isNull("retry_at")) null else block.optString("retry_at")
    val api = HomeApi(LocalContext.current)
    val scope = rememberCoroutineScope()
    val submission = rememberSaveable(id, revision) { UUID.randomUUID().toString() }
    var busy by remember(id, revision) { mutableStateOf(false) }
    var feedback by remember(id, revision) { mutableStateOf<String?>(null) }
    Text("$product · $operation", style = ChatApparatus)
    Text(feedback ?: when (state) {
        "resolved" -> "resolved"
        "checking" -> "checking with google"
        "waiting" -> if (reason == "approval_busy") "another google choice is open. this will retry after it closes"
            else retryAt?.let { "retrying " + DateTimeFormatter.ofPattern("h:mm a").withZone(ZoneId.systemDefault()).format(Instant.parse(it)) }
                ?: "retrying when google is available"
        "superseded" -> when (reason) {
            "consent_expired" -> "google’s request expired"
            "source_changed" -> "the workspace connection changed. start a fresh request"
            "uncertain" -> "the original change is still unconfirmed"
            "target_observed" -> "the intended state is visible now. the original change is still unconfirmed"
            "target_differs" -> "the current state differs. the original change is still unconfirmed"
            else -> "this request is no longer current"
        }
        "denied" -> when (reason) {
            "denied" -> "request denied"
            "policy_block" -> "google blocked this under its policy"
            "screened", "withheld" -> "some content was withheld"
            "partial" -> "some results were unavailable"
            "not_found" -> "google could not confirm that this item is available"
            "exhausted" -> "couldn’t complete this after retrying"
            else -> "this operation is unavailable"
        }
        "needs_owner" -> when (remedy) {
            "answer_google" -> if (reason == "consent_expired") "google’s choice expired. resume to ask again"
                else "google needs a choice before this can continue"
            "reconnect" -> "reconnect $product to jarvis, then retry"
            "verify" -> if (reason == "label_still_present")
                "remove jarvis’s pending label from the affected message in gmail, then verify"
                else "the original result still needs verification"
            else -> "this operation is unavailable"
        }
        else -> "this operation is unavailable"
    }, style = ChatMurmur)
    if (state != "needs_owner") return
    val label = when (remedy) {
        "reconnect" -> "check connection"
        "answer_google" -> "resume $product"
        "verify" -> "verify result"
        else -> return
    }
    TextButton(enabled = !busy, onClick = {
        busy = true
        scope.launch {
            val body = JSONObject().put("revision", revision).put("submission_id", submission)
                .toString().toRequestBody(jsonMedia)
            try {
                api.request("/api/workspace/blocks/$id/resume", "POST", body).use { response ->
                    feedback = when (response.code) {
                        202 -> "checking with google"
                        409 -> if (remedy == "answer_google") "answer google’s open request if shown" else "this request has changed"
                        410 -> "this request is no longer current"
                        426 -> "update the android app to continue"
                        else -> "couldn’t confirm this request"
                    }
                    busy = response.code == 202
                }
            } catch (_: SignInRequired) {
                feedback = "sign in to continue"
                busy = false
            } catch (_: IOException) {
                feedback = "couldn’t confirm this request"
                busy = false
            }
        }
    }) { Text(label) }
}

/** A saved notification only reads its dated result. */
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
        val api = HomeApi(this)
        val access = Access.get(this)
        fun open(route: Route) {
            startActivity(Intent(Intent.ACTION_VIEW, Routes.url(route), this, MainActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP))
            finish()
        }
        setContent {
            val auth by access.revision.collectAsState()
            var status by remember(auth) { mutableStateOf("opening dated result…") }
            var signedOut by remember(auth) { mutableStateOf(false) }
            LaunchedEffect(auth) {
                try {
                    val result = api.read("/api/todos/$todo/occurrences/$occurrence")
                    val id = result?.optString("message_id")
                    if (id != null && canonicalUuid(id)) open(Route.Message(id))
                    else status = "this dated result is unavailable"
                } catch (_: SignInRequired) {
                    signedOut = true
                    status = "sign in to open the dated result"
                } catch (_: IOException) {
                    status = "couldn’t open the dated result"
                } catch (_: JSONException) {
                    status = "couldn’t open the dated result"
                }
            }
            JarvisPaper {
                Pane {
                    Text(status)
                    if (signedOut) TextButton(onClick = { access.signIn(this@WorkspaceTapActivity) }) { Text("sign in") }
                    TextButton(onClick = { open(Route.Todo(todo)) }) { Text("open todo and earlier results") }
                }
            }
        }
    }
}
