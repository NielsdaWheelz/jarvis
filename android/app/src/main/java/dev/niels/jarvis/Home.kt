package dev.niels.jarvis

import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.Intent
import android.net.Uri
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.saveable.rememberSaveableStateHolder
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.LinkAnnotation
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextLinkStyles
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.withLink
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import java.io.IOException
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale
import java.util.UUID
import kotlinx.coroutines.launch
import org.json.JSONException
import org.json.JSONObject

@Composable
internal fun JarvisHome(route: Route, onNavigate: (Route) -> Unit, onBack: (() -> Unit)?, onAlerts: () -> Unit) {
    val context = LocalContext.current
    val activity = context as Activity
    val access = remember { Access.get(context) }
    val api = remember { HomeApi(context) }
    val drafts = remember { Drafts.get(context) }
    val scope = rememberCoroutineScope()
    var chat by rememberSaveable { mutableStateOf(false) }
    var showDrafts by rememberSaveable { mutableStateOf(false) }
    var draftId by rememberSaveable { mutableStateOf<String?>(null) }
    var creating by remember { mutableStateOf(false) }
    var localError by remember { mutableStateOf<String?>(null) }
    val panes = rememberSaveableStateHolder()
    val closeOverlay = {
        if (showDrafts) showDrafts = false else chat = false
    }
    BackHandler(enabled = draftId == null && (showDrafts || chat), onBack = closeOverlay)
    var refresh by remember { mutableIntStateOf(0) }
    val authRevision by access.revision.collectAsState()
    val reload = refresh to authRevision
    val signIn = { access.signIn(activity) }
    DisposableEffect(activity) {
        val lifecycle = (activity as androidx.lifecycle.LifecycleOwner).lifecycle
        val listener = LifecycleEventObserver { _, event -> if (event == Lifecycle.Event.ON_RESUME) refresh++ }
        lifecycle.addObserver(listener)
        onDispose { lifecycle.removeObserver(listener) }
    }

    val newDraft: (DiscussionRef?) -> Unit = { ref ->
        if (!creating) {
            creating = true
            scope.launch {
                try {
                    draftId = drafts.create(UUID.randomUUID().toString(), ref).id
                    showDrafts = false
                    localError = null
                } catch (_: IOException) {
                    localError = "could not save a draft on this phone"
                } finally {
                    creating = false
                }
            }
        }
    }
    JarvisPaper {
        Column(Modifier.fillMaxSize().windowInsetsPadding(WindowInsets.safeDrawing).imePadding()) {
            val currentDraft = draftId
            if (currentDraft != null) {
                DraftComposer(currentDraft, onReturn = { draftId = null }) { messageId ->
                    draftId = null
                    refresh++
                    onNavigate(Route.Message(messageId))
                }
            } else {
                FlowRow(Modifier.padding(horizontal = 8.dp), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    val back = if (chat || showDrafts) closeOverlay else onBack
                    back?.let { TextButton(onClick = it) { Text("back") } }
                    if (route != Route.Overview || chat || showDrafts) {
                        TextButton(onClick = {
                            chat = false
                            showDrafts = false
                            if (route != Route.Overview) onNavigate(Route.Overview)
                        }) { Text("todos") }
                    }
                    if (!chat || showDrafts) TextButton(onClick = {
                        showDrafts = false
                        chat = true
                    }) { Text("chat") }
                    if (!showDrafts) TextButton(onClick = { showDrafts = true }) { Text("drafts") }
                    TextButton(onClick = onAlerts) { Text("alerts") }
                    if (!showDrafts) TextButton(onClick = { refresh++ }) { Text("refresh") }
                }
                HorizontalDivider()
                localError?.let { BodyStatus(it) }
                val pane = when {
                    showDrafts -> "drafts"
                    chat -> "chat"
                    else -> "current"
                }
                if (pane == "chat" || (pane == "current" && route is Route.Message)) {
                    WorkspaceApprovalPanel(api, authRevision)
                }
                panes.SaveableStateProvider(pane) {
                    when {
                        showDrafts -> DraftList(drafts, { draftId = it }, { newDraft(null) })
                        chat -> Conversation(api, reload, signIn, onNavigate, newDraft)
                        else -> when (route) {
                            Route.Home -> Read("home", reload, signIn, { api.read("/api/home") }) { home ->
                                if (home == null) {
                                    Pane { BodyStatus("home unavailable") }
                                } else {
                                    val selected = DiscussionRef.parse(home.optJSONObject("view")) as? DiscussionRef.Canvas
                                    LaunchedEffect(selected) { onNavigate(selected?.route() ?: Route.Overview) }
                                    Pane { BodyStatus("opening home") }
                                }
                            }
                            Route.Overview -> Overview(api, reload, signIn, onNavigate)
                            is Route.Message -> MessageDetail(route, api, reload, signIn, onNavigate, newDraft) {
                                chat = true
                            }
                            is Route.Todo -> TodoDetail(route, api, reload, signIn, onNavigate, newDraft)
                            is Route.File -> FilePane(route, api, reload, signIn, newDraft)
                            is Route.Canvas -> CanvasPane(route, api, reload, signIn, activity, onNavigate, newDraft)
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun DraftList(drafts: Drafts, open: (String) -> Unit, newDraft: () -> Unit) {
    val revision by drafts.revision.collectAsState()
    var items by remember { mutableStateOf<List<Draft>>(emptyList()) }
    var error by remember { mutableStateOf(false) }
    LaunchedEffect(revision) {
        try {
            items = drafts.list()
            error = false
        } catch (_: IOException) {
            error = true
        }
    }
    LazyColumn(contentPadding = PaddingValues(20.dp)) {
        item { Heading("saved drafts") }
        item { TextButton(onClick = newDraft) { Text("new message") } }
        if (error) item { BodyStatus("could not read drafts saved on this phone") }
        if (items.isEmpty() && !error) item { Text("no drafts saved on this phone") }
        items(items, key = { it.id }) { draft ->
            TextButton(onClick = { open(draft.id) }, modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.fillMaxWidth()) {
                    Text(draft.text.lineSequence().firstOrNull { it.isNotBlank() }?.take(120)
                        ?: draft.files.firstOrNull()?.name ?: draft.ref?.label ?: "untitled draft")
                    Text(when (draft.state) {
                        DraftState.Editing -> "saved on this phone"
                        DraftState.Frozen -> "send unconfirmed"
                        DraftState.Conflict -> "submission conflict"
                        DraftState.Received -> "received"
                    }, style = MaterialTheme.typography.labelMedium)
                }
            }
        }
    }
}

@Composable
private fun Overview(api: HomeApi, reload: Pair<Int, Int>, signIn: () -> Unit, navigate: (Route) -> Unit) {
    var offset by rememberSaveable { mutableIntStateOf(0) }
    var expanded by rememberSaveable { mutableStateOf(false) }
    Read(offset, reload, signIn, { api.read("/api/todos?offset=$offset") }) { page ->
        if (page == null) {
            Pane { BodyStatus("overview unavailable") }
            return@Read
        }
        val all = page.objects("items")
        val actualOffset = page.optInt("offset")
        val total = page.optInt("total")
        val zone = page.string("timezone")
        val today = page.getString("today")
        val backlog = page.optInt("backlog_remaining")
        val orderedSections = all.groupBy { it.getString("section") }
        LazyColumn(contentPadding = PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
            item("heading") { Heading("todos") }
            if (all.isEmpty()) item("empty") { Text("no active todos") }
            for ((section, rows) in orderedSections) {
                item("section-$section") {
                    Text(
                        if (section == "backlog") "$backlog in backlog" else section.replace('_', ' '),
                        Modifier.padding(top = 12.dp).semantics { heading() },
                        style = MaterialTheme.typography.titleMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                val collapsed = section == "backlog" && actualOffset == 0
                items(if (collapsed && !expanded) rows.take(2) else rows, key = { it.getString("id") }) { todo ->
                    val due = todo.string("due_date")
                    val state = todo.getString("state")
                    val caption = listOfNotNull(
                        due?.let { (if (it < today) "overdue" else if (it == today) "due today" else "due") + " · " + civilDate(it) },
                        state.replace('_', ' ').takeIf { state != section },
                    ).joinToString(" · ")
                    TextButton(onClick = { navigate(Route.Todo(todo.getString("id"))) }, modifier = Modifier.fillMaxWidth()) {
                        Column(Modifier.fillMaxWidth()) {
                            Text(todo.getString("title"), style = MaterialTheme.typography.titleMedium)
                            if (caption.isNotEmpty()) Text(caption, style = MaterialTheme.typography.labelMedium)
                        }
                    }
                    HorizontalDivider()
                }
                if (collapsed && rows.size > 2) item("disclosure") {
                    TextButton(onClick = { expanded = !expanded }) { Text(if (expanded) "show less" else "show more") }
                }
            }
            if (total > 50) item("paging") {
                FlowRow {
                    TextButton(enabled = actualOffset > 0, onClick = {
                        offset = (actualOffset - 50).coerceAtLeast(0)
                        expanded = false
                    }) {
                        Text("previous page")
                    }
                    TextButton(enabled = actualOffset + all.size < total, onClick = {
                        offset = actualOffset + 50
                        expanded = false
                    }) {
                        Text("next page")
                    }
                }
                Text("${actualOffset + 1}–${actualOffset + all.size} of $total")
            }
            item("checked") { BodyStatus("checked ${formattedTime(page.string("as_of"), zone)}") }
        }
    }
}

@Composable
private fun TodoDetail(
    route: Route.Todo,
    api: HomeApi,
    reload: Pair<Int, Int>,
    signIn: () -> Unit,
    navigate: (Route) -> Unit,
    discuss: (DiscussionRef?) -> Unit,
) {
    var before by rememberSaveable { mutableStateOf<String?>(null) }
    val path = "/api/todos/${route.id}"
    Read(path, reload, signIn, { api.read(path) }) { data ->
        val todo = data?.optJSONObject("record")
        if (todo == null) {
            Pane { BodyStatus("this todo is no longer available") }
            return@Read
        }
        val zone = data.string("timezone")
        Pane {
            Heading(todo.getString("title"))
            BodyStatus(todo.getString("state").replace('_', ' '))
            Prose(todo.getString("content"), navigate)
            todo.string("due_date")?.let { Text("due · ${civilDate(it)}") }
            todo.string("wake_at")?.let {
                val past = Instant.parse(it) <= Instant.parse(data.getString("as_of"))
                Text("jarvis check ${if (past) "was due" else "scheduled for"} ${formattedTime(it, zone)}")
            }
            BodyStatus("checked ${formattedTime(data.string("as_of"), zone)}")
            TextButton(onClick = { discuss(DiscussionRef.Todo(route.id)) }) { Text("discuss this todo") }
            val resultsPath = "$path/results" + (before?.let { "?before=${Uri.encode(it)}" } ?: "")
            Read(resultsPath, reload, signIn, { api.read(resultsPath) }) { results ->
                val items = results?.objects("items").orEmpty()
                if (before != null || items.isNotEmpty()) {
                    HorizontalDivider()
                    Section("linked results")
                    for (result in items) {
                        TextButton(onClick = { navigate(Route.Message(result.getString("message_id"))) }) {
                            Column {
                                Text(result.getString("label").ifBlank { "open result" })
                                Text(formattedTime(result.string("at"), zone), style = MaterialTheme.typography.labelMedium)
                            }
                        }
                    }
                    results?.string("next_before")?.let { edge ->
                        TextButton(onClick = { before = edge }) { Text("earlier results") }
                    }
                    if (before != null) TextButton(onClick = { before = null }) { Text("latest results") }
                }
            }
        }
    }
}

@Composable
private fun Conversation(
    api: HomeApi,
    reload: Pair<Int, Int>,
    signIn: () -> Unit,
    navigate: (Route) -> Unit,
    discuss: (DiscussionRef?) -> Unit,
) {
    var before by rememberSaveable { mutableStateOf<String?>(null) }
    val path = "/api/messages" + (before?.let { "?before=${Uri.encode(it)}" } ?: "")
    Read(path, reload, signIn, { api.read(path) }) { page ->
        LazyColumn(contentPadding = PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            item("heading") { Heading("chat") }
            item("write") { TextButton(onClick = { discuss(null) }) { Text("new message") } }
            if (before != null) item("latest") { TextButton(onClick = { before = null }) { Text("latest messages") } }
            page?.string("next_before")?.let { edge ->
                item("previous") { TextButton(onClick = { before = edge }) { Text("earlier messages") } }
            }
            val messages = page?.objects("items").orEmpty()
            if (messages.isEmpty()) item("empty") { Text("no messages here") }
            items(messages, key = { it.getString("id") }) { message ->
                MessageEntry(message, navigate, discuss)
                TextButton(onClick = { navigate(Route.Message(message.getString("id"))) }) { Text("open exact message") }
                HorizontalDivider()
            }
        }
    }
}

@Composable
private fun MessageDetail(
    route: Route.Message,
    api: HomeApi,
    reload: Pair<Int, Int>,
    signIn: () -> Unit,
    navigate: (Route) -> Unit,
    discuss: (DiscussionRef?) -> Unit,
    conversation: () -> Unit,
) {
    val path = "/api/messages/${route.id}"
    var showMail by rememberSaveable { mutableStateOf(false) }
    Read(path, reload, signIn, { api.read(path) }, signInLabel = "sign in to open this reply") { message ->
        Pane {
            if (message == null) {
                BodyStatus("this message is no longer available")
                return@Pane
            }
            val saved = message.optJSONObject("saved_draft")
            val proposals = message.objects("proposals")
            Heading("message")
            MessageEntry(message, navigate, discuss)
            if (message.string("saved_draft_error") == "integrity") {
                BodyStatus("saved draft receipt failed integrity checks")
            }
            if (saved != null) {
                HorizontalDivider()
                Section("draft revision verified at ${formattedTime(saved.string("observed_at"))}")
                Text(saved.getString("subject"))
                for (field in listOf("to", "cc", "bcc")) {
                    val recipients = saved.objects(field)
                    if (recipients.isNotEmpty()) Text("$field · " + recipients.joinToString(", ") { mailbox ->
                        val address = mailbox.getString("address")
                        mailbox.string("name")?.takeUnless(String::isBlank)?.let { "$it <$address>" } ?: address
                    })
                }
                for (file in saved.objects("files")) {
                    Text("${file.getString("filename")} · ${android.text.format.Formatter.formatFileSize(LocalContext.current, file.getLong("size_bytes"))}")
                }
            }
            if (saved != null || proposals.any { it.optBoolean("read_email") }) {
                TextButton(onClick = { showMail = !showMail }) {
                    Text(if (showMail) "hide email text" else if (saved != null) "read saved draft" else "read email")
                }
                if (showMail) Read("$path?mail_body=true", reload, signIn, { api.read("$path?mail_body=true") }) { expanded ->
                    if (saved != null) {
                        val body = expanded?.optJSONObject("saved_draft")?.string("body_text")
                        Text(body?.ifBlank { "empty email body" } ?: "saved draft text unavailable")
                    }
                    for (proposal in expanded?.objects("proposals").orEmpty()) {
                        proposal.string("mail_body")?.let { text ->
                            Text(proposal.getString("title"), style = MaterialTheme.typography.titleMedium)
                            Text(text.ifBlank { "empty email body" })
                        }
                    }
                }
            }
            TextButton(onClick = conversation) { Text("all conversation") }
        }
    }
}

@Composable
private fun MessageEntry(message: JSONObject, navigate: (Route) -> Unit, discuss: (DiscussionRef?) -> Unit) {
    val id = message.getString("id")
    val speaker = if (message.getString("role") == "owner") "you" else "jarvis"
    Text("$speaker · ${formattedTime(message.string("at"))}", style = MaterialTheme.typography.labelMedium)
    Prose(message.getString("text"), navigate)
    for (file in message.objects("files")) {
        val status = if (file.optBoolean("unavailable")) "original unavailable" else when (file.string("state")) {
            "pending" -> "saving original"
            "ready" -> "open original"
            "deleted" -> "original deleted"
            "deleting" -> "deleting original"
            else -> "original unavailable"
        }
        TextButton(onClick = { navigate(Route.File(file.getString("id"), null)) }) {
            Text("${file.string("name") ?: "original file"} · $status")
        }
    }
    DiscussionRef.parse(message.optJSONObject("ref"))?.let { ref ->
        TextButton(onClick = { navigate(ref.route()) }) { Text("discussed · ${ref.label}") }
    }
    for (proposal in message.objects("proposals")) {
        HorizontalDivider()
        Section(proposal.getString("title"))
        if (proposal.optBoolean("read_email")) Text(proposal.getString("detail"))
        else Prose(proposal.getString("detail"), navigate)
        BodyStatus(proposal.string("status_label") ?: proposal.getString("status").replace('_', ' '))
        proposal.string("owner_message_id")?.let { owner ->
            TextButton(onClick = { navigate(Route.Message(owner)) }) { Text("owner reply · ${proposal.getString("decision")}") }
        }
        TextButton(onClick = { discuss(DiscussionRef.Proposal(id, proposal.getString("action_id"))) }) {
            Text("reply to ${proposal.getString("title")}")
        }
    }
    DiscussionRef.parse(message.optJSONObject("present")?.optJSONObject("ref"))?.let { ref ->
        TextButton(onClick = { navigate(ref.route()) }) { Text("open ${ref.label}") }
    }
}

@Composable
private fun CanvasPane(
    route: Route.Canvas,
    api: HomeApi,
    reload: Pair<Int, Int>,
    signIn: () -> Unit,
    activity: Activity,
    navigate: (Route) -> Unit,
    discuss: (DiscussionRef?) -> Unit,
) {
    val path = "/api/views/${route.slug}" + (route.revision?.let { "/$it" } ?: "")
    var opened by rememberSaveable { mutableStateOf(false) }
    var browserError by remember { mutableStateOf(false) }
    Read(path, reload, signIn, { api.read(path) }) { data ->
        Pane {
            val ref = DiscussionRef.parse(data) as? DiscussionRef.Canvas
            if (ref == null) {
                BodyStatus("this page is no longer available")
                return@Pane
            }
            val open = { browserError = !Routes.openCanvas(activity, Route.Canvas(ref.slug, ref.revision)) }
            LaunchedEffect(ref) {
                if (route.revision == null) navigate(ref.route())
                else if (!opened) {
                    opened = true
                    open()
                }
            }
            Heading(ref.slug)
            TextButton(onClick = open) { Text("open published page in browser") }
            if (browserError) BodyStatus("browser unavailable")
            TextButton(onClick = { discuss(ref) }) { Text("discuss this page") }
        }
    }
}

@Composable
internal fun Pane(content: @Composable ColumnScope.() -> Unit) {
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
        content = content,
    )
}

@Composable
internal fun Section(title: String) {
    Text(title, Modifier.semantics { heading() }, style = MaterialTheme.typography.titleMedium)
}

private data class Snapshot<T>(val value: T?, val checked: Instant)

@Composable
internal fun <T> Read(
    key: Any,
    reload: Pair<Int, Int>,
    signIn: () -> Unit,
    load: suspend () -> T?,
    signInLabel: String = "sign in to continue",
    content: @Composable (T?) -> Unit,
) {
    var snapshot by remember(key) { mutableStateOf<Snapshot<T>?>(null) }
    var error by remember(key) { mutableStateOf<String?>(null) }
    var attempt by remember(key) { mutableIntStateOf(0) }
    LaunchedEffect(key, reload, attempt) {
        try {
            snapshot = Snapshot(load(), Instant.now())
            error = null
        } catch (_: SignInRequired) {
            error = signInLabel
        } catch (_: IOException) {
            error = "could not refresh"
        } catch (_: JSONException) {
            error = "could not read this response"
        }
    }
    val current = snapshot
    val problem = error
    if (problem != null) {
        Column(Modifier.padding(horizontal = 20.dp)) {
            BodyStatus(problem + (current?.let { " · last checked ${formattedTime(it.checked.toString())}" } ?: ""))
            if (problem == signInLabel) TextButton(onClick = signIn) { Text("sign in") }
            else TextButton(onClick = { attempt++ }) { Text("retry") }
        }
    }
    if (current != null) content(current.value)
    else if (problem == null) CircularProgressIndicator(Modifier.padding(20.dp))
}

internal fun formattedTime(value: String?, timezone: String? = null): String {
    if (value == null) return ""
    val zone = timezone?.let(ZoneId::of) ?: ZoneId.systemDefault()
    return DateTimeFormatter.ofPattern("MMM d, h:mm a${if (timezone != null) " z" else ""}", Locale.getDefault())
        .withZone(zone).format(Instant.parse(value))
}

private fun civilDate(value: String): String =
    LocalDate.parse(value).format(DateTimeFormatter.ofPattern("MMM d", Locale.getDefault()))

private val LinkStart = Regex(
    """\[([^\]\n]+)]\((?=https?://|/[mftv]/)|attachment:([0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12})|(?:https?://|/[mftv]/)[^\s<>]+""",
    RegexOption.IGNORE_CASE,
)

@Composable
internal fun Prose(text: String, navigate: (Route) -> Unit) {
    val context = LocalContext.current
    val color = MaterialTheme.colorScheme.primary
    val annotated = buildAnnotatedString {
        var end = 0
        while (end < text.length) {
            val match = LinkStart.find(text, end) ?: break
            val label = match.groups[1]?.value
            val original = match.groups[2]?.value
            var next = match.range.last + 1
            val href = when {
                label != null -> {
                    val parsed = labeledDestination(text, next)
                    if (parsed == null) {
                        append(text.substring(end, next))
                        end = next
                        continue
                    }
                    next = parsed.second
                    parsed.first
                }
                original != null -> "/f/$original"
                else -> match.value.trimEnd('.', ',', ';', ':', '!', '?', '\'', '"', ']', '}').let { candidate ->
                    if (candidate.endsWith(')') && candidate.count { it == ')' } > candidate.count { it == '(' })
                        candidate.dropLast(1) else candidate
                }
            }
            val uri = Uri.parse(href)
            val route = hrefRoute(href)
            val external = route == null && uri.scheme in setOf("http", "https") &&
                !uri.host.isNullOrBlank() && uri.userInfo == null
            if (route == null && !external) {
                append(text.substring(end, next))
                end = next
                continue
            }
            append(text.substring(end, match.range.first))
            withLink(LinkAnnotation.Clickable(href, TextLinkStyles(style = SpanStyle(color = color, textDecoration = TextDecoration.Underline))) {
                if (route != null) navigate(route)
                else try {
                    context.startActivity(Intent(Intent.ACTION_VIEW, uri))
                } catch (_: ActivityNotFoundException) {
                    android.widget.Toast.makeText(context, "browser unavailable", android.widget.Toast.LENGTH_SHORT).show()
                }
            }) { append(label ?: if (original != null) "original file" else href) }
            if (label == null && original == null) append(match.value.substring(href.length))
            end = next
        }
        append(text.substring(end))
    }
    Text(annotated)
}

private fun labeledDestination(text: String, start: Int): Pair<String, Int>? {
    val href = StringBuilder()
    var depth = 0
    var index = start
    while (index < text.length) {
        val c = text[index++]
        when {
            c.isWhitespace() || c == '<' || c == '>' -> return null
            c == ')' && depth == 0 -> return href.toString() to index
            c == '\\' && index < text.length && text[index] in "()\\" -> href.append(text[index++])
            else -> {
                if (c == '(') depth++
                if (c == ')') depth--
                href.append(c)
            }
        }
    }
    return null
}
