package dev.niels.jarvis

import android.graphics.Bitmap
import android.os.SystemClock
import android.text.format.Formatter
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.Image
import androidx.compose.foundation.content.consume
import androidx.compose.foundation.content.contentReceiver
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.input.TextFieldLineLimits
import androidx.compose.foundation.text.input.TextFieldState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.input.key.KeyEventType
import androidx.compose.ui.input.key.isCtrlPressed
import androidx.compose.ui.input.key.isMetaPressed
import androidx.compose.ui.input.key.key
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.input.key.type
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay

@OptIn(ExperimentalFoundationApi::class)
@Composable
internal fun ChatDock(
    drafts: Drafts, focusRequest: Int, requestedReference: DiscussionRef?,
    closeReference: () -> Unit, send: (String) -> Unit,
) {
    val colors = MaterialTheme.colorScheme
    val draft = drafts.draft
    if (draft == null) {
        if (drafts.problem != null) BodyStatus(checkNotNull(drafts.problem))
        return
    }
    val context = LocalContext.current
    val keyboard = LocalSoftwareKeyboardController.current
    val field = remember { FocusRequester() }
    val keep = remember { FocusRequester() }
    val input = remember(draft.id) { TextFieldState(draft.text) }
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { drafts.append(it) }
    var focused by remember { mutableStateOf(false) }
    var confirmDiscard by remember(draft.id) { mutableStateOf(false) }
    var sendingWords by remember(drafts.sendingSince) { mutableStateOf(false) }
    var mayStop by remember(drafts.sendingSince) { mutableStateOf(false) }
    var focusedRequest by remember { mutableStateOf(0) }
    val words = input.text.toString()
    val sending = drafts.sending
    val held = draft.held && !sending
    val ready = !sending && drafts.copying == 0 && draft.canSend(words)
    val style = chatBody(owner = true)
    val strokeY = with(LocalDensity.current) { (style.fontSize.toPx() * 1.5f) / 2 }
    val problem = drafts.problem ?: "message or files are too large.".takeIf {
        words.toByteArray(Charsets.UTF_8).size > TextLimit
    }
    fun keepWords() {
        confirmDiscard = false
        closeReference()
        field.requestFocus()
    }
    fun submit() {
        if (!ready || confirmDiscard || requestedReference != null) return
        field.requestFocus()
        send(words)
    }
    LaunchedEffect(input, draft.id) {
        snapshotFlow { input.text.toString() }.collect { drafts.edit(draft.id, it) }
    }
    LaunchedEffect(focusRequest) {
        if (focusRequest != focusedRequest && focusRequest > 0) {
            focusedRequest = focusRequest
            field.requestFocus()
            keyboard?.show()
        }
    }
    LaunchedEffect(confirmDiscard, requestedReference) {
        if (confirmDiscard || requestedReference != null) keep.requestFocus()
    }
    LaunchedEffect(drafts.sendingSince) {
        val began = drafts.sendingSince ?: return@LaunchedEffect
        delay((began + 400 - SystemClock.elapsedRealtime()).coerceAtLeast(0))
        sendingWords = true
        delay((began + 10_000 - SystemClock.elapsedRealtime()).coerceAtLeast(0))
        mayStop = true
    }
    BackHandler(enabled = confirmDiscard || requestedReference != null, onBack = ::keepWords)
    Column(Modifier.fillMaxWidth().onPreviewKeyEvent {
        if (it.type != KeyEventType.KeyDown) return@onPreviewKeyEvent false
        when {
            it.key == Key.Escape && (confirmDiscard || requestedReference != null) -> {
                keepWords()
                true
            }
            it.key == Key.Enter && (it.isCtrlPressed || it.isMetaPressed) -> {
                submit()
                true
            }
            else -> false
        }
    }.drawBehind {
        val width = if (focused && !drafts.locked) 2.dp.toPx() else 1.dp.toPx()
        drawLine(
            if (focused && !drafts.locked) colors.onSurface else colors.outlineVariant,
            Offset(0f, width / 2), Offset(size.width, width / 2), width,
        )
    }.padding(start = 24.dp, end = 16.dp, top = 8.dp)) {
        if (draft.ref != null || requestedReference != null || draft.files.isNotEmpty()) {
            Column(Modifier.heightIn(max = 144.dp).verticalScroll(rememberScrollState())) {
                if (requestedReference != null) {
                    Text("change the reference to ${requestedReference.label}?", style = ChatMurmur)
                    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        ChatWord("keep draft", ::keepWords, Modifier.focusRequester(keep))
                        ChatWord("use this item", {
                            drafts.reference(requestedReference)
                            keepWords()
                        })
                    }
                } else draft.ref?.let { ref ->
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("about · ${ref.label}", Modifier.weight(1f), style = ChatApparatus)
                        if (!drafts.locked) ChatWord("×", { drafts.reference(null) }, label = "remove reference")
                    }
                }
                for (file in draft.files) key(draft.id, file.slot) {
                    val thumbnail by produceState<Bitmap?>(null, file.sha256) {
                        if (file.sha256 != null) value = drafts.thumbnail(file.slot)
                    }
                    Row(Modifier.fillMaxWidth().heightIn(min = 48.dp), verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Box(Modifier.size(40.dp), contentAlignment = Alignment.Center) {
                            thumbnail?.let { Image(it.asImageBitmap(), null, Modifier.size(40.dp)) }
                                ?: Text(file.name.substringAfterLast('.', "").take(5), style = ChatCaps)
                        }
                        Column(Modifier.weight(1f)) {
                            Text(file.name, maxLines = 2, overflow = TextOverflow.Ellipsis, style = ChatApparatus)
                            file.problem?.let { Text(it, style = ChatMurmur, color = colors.onSurfaceVariant) }
                        }
                        if (file.problem == null) Text(Formatter.formatShortFileSize(context, file.size).lowercase(), style = ChatCaps)
                        if (!drafts.locked) ChatWord("×", { drafts.remove(file.slot) }, label = "remove ${file.name}")
                    }
                }
            }
        }
        BasicTextField(
            state = input, readOnly = drafts.locked, textStyle = style.copy(
                color = if (sending) colors.onSurface.copy(alpha = .58f) else colors.onSurface,
            ),
            cursorBrush = SolidColor(if (drafts.locked) Color.Transparent else colors.onSurface),
            lineLimits = TextFieldLineLimits.MultiLine(minHeightInLines = 1, maxHeightInLines = 6),
            modifier = Modifier.fillMaxWidth().focusRequester(field).onFocusChanged { focused = it.isFocused }
                .semantics { contentDescription = "to jarvis" }
                .drawBehind {
                    drawLine(colors.onSurfaceVariant, Offset(-18.dp.toPx(), strokeY),
                        Offset(-9.dp.toPx(), strokeY), 1.5.dp.toPx())
                }
                .then(if (drafts.locked) Modifier else Modifier.contentReceiver { content ->
                    val uris = mutableListOf<android.net.Uri>()
                    val remainder = content.consume { item ->
                        val uri = item.uri
                        if (uri?.scheme == "content") uris.add(uri) else false
                    }
                    if (uris.isNotEmpty()) drafts.append(uris, content.platformTransferableContent?.extras)
                    remainder
                }),
            decorator = { inner ->
                Box(Modifier.fillMaxWidth()) {
                    if (words.isEmpty()) Text("to jarvis", color = colors.onSurfaceVariant, style = ChatMurmur)
                    inner()
                }
            },
        )
        problem?.let { Text(it, style = ChatMurmur, modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite }) }
        when {
            confirmDiscard -> {
                Text("discard these words? a send that did arrive stays in the conversation.", style = ChatMurmur)
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    ChatWord("keep", ::keepWords, Modifier.focusRequester(keep))
                    ChatWord("discard", {
                        confirmDiscard = false
                        drafts.discard()
                        field.requestFocus()
                    })
                }
            }
            held -> {
                Text(if (drafts.receiptChecked) ReceiptUnknown else "checking whether your message arrived…",
                    color = colors.onSurfaceVariant, style = ChatMurmur)
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    ChatWord("retry", ::submit, enabled = ready)
                    ChatWord("discard", { confirmDiscard = true })
                }
            }
            sending -> Row(Modifier.fillMaxWidth().heightIn(min = 48.dp), verticalAlignment = Alignment.CenterVertically) {
                if (sendingWords) Text("sending…", Modifier.weight(1f), color = colors.onSurfaceVariant, style = ChatMurmur)
                if (mayStop) ChatWord("stop waiting", drafts::stopWaiting)
            }
            else -> Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween) {
                ChatWord("attach", { picker.launch(arrayOf("*/*")) })
                if (drafts.copying > 0) Text("adding files", color = colors.onSurfaceVariant, style = ChatMurmur)
                ChatWord("send", ::submit, enabled = ready)
            }
        }
    }
}
