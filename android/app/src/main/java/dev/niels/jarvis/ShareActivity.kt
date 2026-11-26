package dev.niels.jarvis

import android.app.Activity
import android.content.Intent
import android.graphics.Bitmap
import android.net.Uri
import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.Image
import androidx.compose.foundation.content.consume
import androidx.compose.foundation.content.contentReceiver
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.input.TextFieldLineLimits
import androidx.compose.foundation.text.input.TextFieldState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.produceState
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import java.io.IOException
import java.util.UUID
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

class ShareActivity : ComponentActivity() {
    private lateinit var draftId: String

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        draftId = savedInstanceState?.getString("draftId") ?: UUID.randomUUID().toString()
        val drafts = Drafts.get(this)
        val capture = ViewModelProvider(this)[ShareCapture::class.java]
        capture.receive(drafts, draftId, intent)
        setContent {
            val state by capture.state.collectAsState()
            JarvisPaper {
                Column(Modifier.fillMaxSize().windowInsetsPadding(WindowInsets.safeDrawing).imePadding()) {
                    when (state) {
                        CaptureState.Copying -> Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                            Heading("copying the shared original")
                            CircularProgressIndicator()
                        }
                        is CaptureState.Unavailable -> Column(Modifier.padding(20.dp)) {
                            Heading("share unavailable")
                            BodyStatus((state as CaptureState.Unavailable).message)
                            TextButton(onClick = ::finish) { Text("return") }
                        }
                        CaptureState.Saved -> DraftComposer(draftId, ::finish) {
                            Toast.makeText(this@ShareActivity, "received", Toast.LENGTH_SHORT).show()
                            finish()
                        }
                    }
                }
            }
        }
    }

    override fun onSaveInstanceState(outState: Bundle) {
        outState.putString("draftId", draftId)
        super.onSaveInstanceState(outState)
    }
}

internal sealed interface CaptureState {
    data object Copying : CaptureState
    data object Saved : CaptureState
    data class Unavailable(val message: String) : CaptureState
}

internal class ShareCapture : ViewModel() {
    private var started = false
    private val result = MutableStateFlow<CaptureState>(CaptureState.Copying)
    internal val state: StateFlow<CaptureState> get() = result

    internal fun receive(drafts: Drafts, id: String, intent: Intent) {
        if (started) return
        started = true
        viewModelScope.launch {
            result.value = try {
                drafts.receive(id, intent)
                CaptureState.Saved
            } catch (_: IOException) {
                CaptureState.Unavailable("could not save this share · re-share to try again")
            } catch (_: SecurityException) {
                CaptureState.Unavailable("could not read this share · re-share to try again")
            }
        }
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
internal fun DraftComposer(id: String, onReturn: () -> Unit, onReceived: (String) -> Unit) {
    val context = LocalContext.current
    val activity = context as Activity
    val drafts = remember { Drafts.get(context) }
    val api = remember { HomeApi(context) }
    val access = remember { Access.get(context) }
    val version by drafts.revision.collectAsState()
    val authVersion by access.revision.collectAsState()
    val changes by drafts.fileChanges.collectAsState()
    val fileChange = changes[id]
    val copying = (fileChange?.copies ?: 0) > 0
    val transfers by drafts.transfers.collectAsState()
    val transfer = transfers[id]
    val active = transfer?.active == true
    var record by remember(id) { mutableStateOf<Draft?>(null) }
    var loadError by remember(id) { mutableStateOf(false) }
    LaunchedEffect(id, version) {
        try {
            record = drafts.get(id)
            loadError = record == null
        } catch (_: IOException) {
            loadError = true
        }
    }
    val draft = record
    if (draft == null) {
        if (loadError) {
            Column(Modifier.padding(20.dp)) {
                BodyStatus("saved draft unavailable")
                TextButton(onClick = onReturn) { Text("return") }
            }
        } else {
            CircularProgressIndicator(Modifier.padding(20.dp))
        }
        return
    }

    val scope = rememberCoroutineScope()
    val editor = rememberSaveable(id, saver = TextFieldState.Saver) { TextFieldState(draft.text) }
    val caption = editor.text.toString()
    var returning by remember(id) { mutableStateOf(false) }
    var confirmDiscard by rememberSaveable { mutableStateOf(false) }
    var checkedAuthVersion by remember(id) { mutableStateOf<Int?>(null) }
    var localError by remember(id) { mutableStateOf<String?>(null) }
    val editable = draft.state == DraftState.Editing && !active
    val valid = caption.toByteArray(Charsets.UTF_8).size <= TextLimit && '\u0000' !in editor.text
    val canSend = !active && !copying && valid && draft.files.none { it.problem != null } &&
        (editor.text.isNotBlank() || draft.files.isNotEmpty()) &&
        draft.state in setOf(DraftState.Editing, DraftState.Frozen) &&
        transfer !in setOf(Transfer.TooLarge, Transfer.Invalid, Transfer.UpdateRequired)

    LaunchedEffect(id, editor) {
        snapshotFlow { editor.text.toString() }.collect { text ->
            try {
                drafts.edit(id, text)
                localError = null
            } catch (_: IOException) {
                localError = "could not save this change"
            }
        }
    }
    LaunchedEffect(id, draft.state, authVersion, transfer) {
        if (transfer == Transfer.Sending) checkedAuthVersion = null
        if (transfer == Transfer.SignedOut) {
            try {
                if (access.currentBearer() != null) drafts.signedIn(id)
            } catch (_: IOException) {
                localError = "could not check sign-in"
            }
        }
        if (draft.state == DraftState.Frozen && checkedAuthVersion != authVersion &&
            transfer in setOf(null, Transfer.Unconfirmed, Transfer.SignedOut)
        ) {
            checkedAuthVersion = authVersion
            drafts.checkReceipt(id, api)
        }
        if (draft.state == DraftState.Received && !active) {
            val receipt = checkNotNull(draft.receipt)
            drafts.discard(id)
            onReceived(receipt)
        }
    }

    fun saveAndReturn() {
        if (returning) return
        returning = true
        val failures = drafts.fileChanges.value[id]?.failures ?: 0
        scope.launch {
            try {
                while (true) {
                    drafts.awaitFileChanges(id)
                    val current = editor.text.toString()
                    drafts.edit(id, current)
                    val latest = drafts.fileChanges.value[id]
                    if ((latest?.failures ?: 0) != failures) return@launch
                    if ((latest?.pending ?: 0) == 0 && current == editor.text.toString()) {
                        onReturn()
                        return@launch
                    }
                }
            } catch (_: IOException) {
                localError = "could not save this change"
            } finally {
                returning = false
            }
        }
    }

    BackHandler(onBack = ::saveAndReturn)
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Heading("message jarvis")
        val status = when (draft.state) {
            DraftState.Editing -> if (copying) "adding files" else transfer?.label ?:
                if (caption == draft.text && (fileChange?.pending ?: 0) == 0) "saved on this phone" else "saving changes"
            DraftState.Frozen -> if (transfer == Transfer.SignedOut) "send unconfirmed · sign in to check receipt"
                else transfer?.label ?: Transfer.Unconfirmed.label
            DraftState.Conflict -> "submission conflict · discard this frozen draft"
            DraftState.Received -> "received"
        }
        BodyStatus(localError ?: status)
        draft.ref?.let { ref ->
            Text("about ${ref.label}", style = MaterialTheme.typography.bodyMedium)
            if (editable) TextButton(onClick = { drafts.remove(id, null) }) {
                Text("remove reference")
            }
        }
        OutlinedTextField(
            state = editor,
            modifier = Modifier.fillMaxWidth().then(if (editable) Modifier.contentReceiver { content ->
                val uris = mutableListOf<Uri>()
                val remainder = content.consume { item ->
                    val uri = item.uri
                    if (uri?.scheme == "content") uris.add(uri) else false
                }
                if (uris.isNotEmpty()) drafts.append(id, uris, content.platformTransferableContent?.extras)
                remainder
            } else Modifier),
            label = { Text("instruction") },
            readOnly = !editable,
            isError = !valid,
            supportingText = if (valid) null else ({ Text("instruction exceeds 16 kib or contains invalid text") }),
            lineLimits = TextFieldLineLimits.MultiLine(minHeightInLines = 4),
        )
        fileChange?.error?.let { BodyStatus(it) }
        for (file in draft.files) key(file.slot, file.sha256) {
            HorizontalDivider()
            if (file.sha256 != null) {
                val preview by produceState<Bitmap?>(null, id, file.slot, file.sha256) {
                    value = drafts.thumbnail(id, file.slot)
                }
                preview?.let { Image(it.asImageBitmap(), null, Modifier.size(64.dp)) }
            }
            Text(file.name)
            if (file.problem != null) BodyStatus(file.problem)
            if (editable) TextButton(onClick = { drafts.remove(id, file.slot) }) {
                Text("remove ${file.name}")
            }
        }
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            if (transfer == Transfer.SignedOut) {
                Button(onClick = { access.signIn(activity) }) { Text("sign in") }
            } else {
                Button(enabled = canSend, onClick = {
                    localError = null
                    drafts.send(id, editor.text.toString(), api)
                }) {
                    Text(if (draft.state == DraftState.Frozen) "retry this submission" else "send")
                }
            }
            TextButton(onClick = ::saveAndReturn) { Text("save and return") }
            TextButton(enabled = !active && (fileChange?.pending ?: 0) == 0, onClick = { confirmDiscard = true }) { Text("discard draft") }
        }
    }
    if (confirmDiscard) {
        AlertDialog(
            onDismissRequest = { confirmDiscard = false },
            title = { Text("discard this draft?") },
            text = {
                Text(if (draft.state == DraftState.Editing) "the copy saved on this phone will be removed."
                else "discarding removes this phone’s copy. an entered send may still arrive.")
            },
            confirmButton = {
                TextButton(onClick = { scope.launch {
                    confirmDiscard = false
                    if (drafts.discard(id)) onReturn() else localError = "could not discard this draft"
                } }) { Text("discard") }
            },
            dismissButton = { TextButton(onClick = { confirmDiscard = false }) { Text("keep draft") } },
        )
    }
}

@Composable
internal fun JarvisPaper(
    modifier: Modifier = Modifier.fillMaxSize(),
    content: @Composable () -> Unit,
) {
    val dark = isSystemInDarkTheme()
    val colors = if (dark) darkColorScheme(
        background = Color(0xFF191B19), surface = Color(0xFF20221F), onSurface = Color(0xFFF3F2E8),
        onBackground = Color(0xFFF3F2E8), primary = Color(0xFFB5CBB7), onPrimary = Color(0xFF1C3524),
        onSurfaceVariant = Color(0xFFACAFA5), outline = Color(0xFF777C73),
    ) else lightColorScheme(
        background = Color(0xFFF4F2EC), surface = Color(0xFFFBFAF6), onSurface = Color(0xFF252621),
        onBackground = Color(0xFF252621), primary = Color(0xFF43564A), onPrimary = Color(0xFFFFFFFF),
        onSurfaceVariant = Color(0xFF64675F), outline = Color(0xFF777C73),
    )
    val type = Typography()
    MaterialTheme(colorScheme = colors, typography = type.copy(
        headlineLarge = type.headlineLarge.copy(fontFamily = FontFamily.Serif),
        headlineSmall = type.headlineSmall.copy(fontFamily = FontFamily.Serif),
    )) {
        Surface(modifier, color = colors.background, contentColor = colors.onBackground, content = content)
    }
}

@Composable
internal fun Heading(text: String) {
    Text(text, Modifier.semantics { heading() }, style = MaterialTheme.typography.headlineLarge)
}

@Composable
internal fun BodyStatus(text: String) {
    Text(text, Modifier.semantics { liveRegion = LiveRegionMode.Polite }, color = MaterialTheme.colorScheme.onSurfaceVariant)
}
