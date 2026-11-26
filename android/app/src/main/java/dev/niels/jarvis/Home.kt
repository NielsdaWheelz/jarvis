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
import androidx.compose.ui.semantics.selected
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
internal fun JarvisHome(
    entry: Route, onNavigate: (Route) -> Unit, onResolve: (Route) -> Unit,
    todoReads: () -> TodoReads, onBack: (() -> Unit)?,
) {
    val context = LocalContext.current
    val activity = context as Activity
    val access = remember { Access.get(context) }
    val api = remember { HomeApi(context) }
    val drafts = remember { Drafts.get(context) }
    val scope = rememberCoroutineScope()
    // Keep the home visit even when it resolves to the same address as a direct link.
    var homeAddress by rememberSaveable { mutableStateOf<String?>(null) }
    val route = if (entry == Route.Home) homeAddress?.let { Routes.parse(Uri.parse(it)) } ?: entry else entry
    val resolve: (Route) -> Unit = { target ->
        if (entry == Route.Home) homeAddress = Routes.url(target).toString() else onResolve(target)
    }
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
    val setupHome = entry == Route.Home && route != Route.Home && !chat && !showDrafts && draftId == null
    val phone = remember { PhoneAlerts.get(context) }
    LaunchedEffect(reload, setupHome) { phone.refresh(setupHome) }
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
                    val destinations = listOf(
                        "jarvis" to Route.Home,
                        "todos" to Route.Todos,
                        "artifacts" to Route.Artifacts,
                        "files" to Route.Files,
                    )
                    val section = when (route) {
                        is Route.Todo -> Route.Todos
                        is Route.Artifact -> Route.Artifacts
                        is Route.File, is Route.DriveFile -> Route.Files
                        else -> route
                    }
                    for ((label, target) in destinations) {
                        val selectedSection = section == target && !chat && !showDrafts
                        TextButton(
                            onClick = {
                                if (entry != target) onNavigate(target)
                                else {
                                    chat = false
                                    showDrafts = false
                                }
                            },
                            modifier = Modifier.semantics { selected = selectedSection },
                        ) { Text(label, style = if (selectedSection) MaterialTheme.typography.titleMedium else MaterialTheme.typography.labelLarge) }
                    }
                    if (!chat || showDrafts) TextButton(onClick = {
                        showDrafts = false
                        chat = true
                    }) { Text("chat") }
                    if (!showDrafts) TextButton(onClick = { showDrafts = true }) { Text("drafts") }
                    if (!showDrafts) TextButton(onClick = { refresh++ }) { Text("refresh") }
                }
                HorizontalDivider()
                if (setupHome) PhoneSetupAction(phone, signIn)
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
                            Route.Home -> Read("home", reload, signIn, api::selectedHome) { selected ->
                                LaunchedEffect(selected) { resolve(selected?.route() ?: Route.Todos) }
                                Pane { BodyStatus("opening home") }
                            }
                            Route.Todos, is Route.Todo -> TodoViewer((route as? Route.Todo)?.id, todoReads(), api, reload, signIn, onNavigate, newDraft)
                            is Route.Message -> MessageDetail(route, api, reload, signIn, onNavigate, newDraft) {
                                chat = true
                            }
                            Route.Files -> DriveList(null, api, reload, signIn, onNavigate, newDraft)
                            is Route.File -> OriginPane(route, api, reload, signIn, onResolve)
                            is Route.DriveFile -> FilePane(route, api, reload, signIn, onNavigate, newDraft)
                            is Route.Mail -> Pane {
                                TextButton(onClick = { onNavigate(route) }) { Text("open in browser") }
                                TextButton(onClick = { onNavigate(Route.Message(route.messageId)) }) { Text("open message") }
                            }
                            Route.Artifacts -> ArtifactShelf(api, reload, signIn, onNavigate)
                            is Route.Artifact -> ArtifactPane(route, api, reload, signIn, activity, resolve, onNavigate, newDraft)
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
            val deliveries = messages.associateWith { it.deliveries() }
            val editions = deliveries.values.flatten().filterIsInstance<DiscussionRef.Artifact>()
            if (messages.isEmpty()) item("empty") { Text("no messages here") }
            items(messages, key = { it.getString("id") }) { message ->
                MessageEntry(message, navigate, discuss, deliveries.getValue(message), editions)
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
    Read(path, reload, signIn, { api.read(path) }, signInLabel = "sign in to open this reply") { message ->
        Pane {
            if (message == null) {
                BodyStatus("this message is no longer available")
                return@Pane
            }
            Heading("message")
            MessageEntry(message, navigate, discuss)
            TextButton(onClick = conversation) { Text("all conversation") }
        }
    }
}

private fun JSONObject.deliveries(): List<DiscussionRef> {
    val links = objects("artifact_links").mapNotNull { DiscussionRef.parse(it) as? DiscussionRef.Artifact }
    val presented = DiscussionRef.parse(optJSONObject("present")?.optJSONObject("ref"))
    return (links + listOfNotNull(presented)).distinct()
}

@Composable
private fun MessageEntry(
    message: JSONObject, navigate: (Route) -> Unit, discuss: (DiscussionRef?) -> Unit,
    deliveries: List<DiscussionRef> = message.deliveries(),
    editions: List<DiscussionRef.Artifact> = deliveries.filterIsInstance<DiscussionRef.Artifact>(),
) {
    val id = message.getString("id")
    val speaker = if (message.getString("role") == "owner") "you" else "jarvis"
    Text("$speaker · ${formattedTime(message.string("at"))}", style = MaterialTheme.typography.labelMedium)
    Prose(message.getString("text"), navigate)
    for (file in message.objects("files")) {
        val status = if (file.optBoolean("unavailable")) "file unavailable" else originStatus(file)
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
        val revision = proposal.string("draft_revision_id")
        if (revision != null) Text(proposal.getString("detail"))
        else Prose(proposal.getString("detail"), navigate)
        BodyStatus(proposal.string("status_label") ?: proposal.getString("status").replace('_', ' '))
        if (revision != null) {
            TextButton(onClick = { navigate(Route.Mail(id, revision, historical = true)) }) {
                Text("open draft revision")
            }
        }
        proposal.string("owner_message_id")?.let { owner ->
            TextButton(onClick = { navigate(Route.Message(owner)) }) { Text("owner reply · ${proposal.getString("decision")}") }
        }
        TextButton(onClick = { discuss(DiscussionRef.Proposal(id, proposal.getString("action_id"))) }) {
            Text("reply to ${proposal.getString("title")}")
        }
    }
    val drafts = message.objects("drafts")
    message.string("draft_revision_id")?.takeUnless { revision ->
        drafts.any { it.opt("editable") != true && it.string("create_action_id") == revision }
    }?.let { revision ->
        TextButton(onClick = { navigate(Route.Mail(id, revision, historical = true)) }) { Text("open draft revision") }
    }
    if (message.string("draft_revision_error") == "integrity") {
        BodyStatus("exact revision failed integrity checks")
    }
    drafts.forEachIndexed { index, created ->
        val action = created.getString("create_action_id")
        val subject = created.string("subject").orEmpty().ifBlank { "(no subject)" }
        val repeated = drafts.count { it.string("subject") == created.string("subject") } > 1
        val ordinal = drafts.take(index + 1).count { it.string("subject") == created.string("subject") }
        val name = if (repeated) "$subject · $ordinal" else subject
        val historical = created.opt("editable") != true
        val label = if (historical) "open draft revision" else "open draft"
        TextButton(onClick = { navigate(Route.Mail(id, action, historical)) }) { Text("$label · $name") }
    }
    for (ref in deliveries) {
        val label = if (ref is DiscussionRef.Artifact) ref.labelAmong(editions) else ref.label
        TextButton(onClick = { navigate(ref.route()) }) { Text("open $label") }
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

internal class ReadState<T> {
    var data by mutableStateOf<T?>(null)
        private set
    private var checked by mutableStateOf<Instant?>(null)
    val received get() = checked != null
    private var error by mutableStateOf<String?>(null)
    val settled get() = received || error != null
    private var attempt by mutableIntStateOf(0)

    @Composable
    fun load(key: Any, reload: Pair<Int, Int>, read: suspend () -> T?) {
        LaunchedEffect(this, key, reload, attempt) {
            try {
                data = read()
                checked = Instant.now()
                error = null
            } catch (_: SignInRequired) {
                data = null
                checked = null
                error = "sign in"
            } catch (update: ViewerUpdateRequired) {
                data = null
                checked = null
                error = update.message
            } catch (_: IOException) {
                error = "could not refresh"
            } catch (_: JSONException) {
                error = "could not read this response"
            }
        }
    }

    @Composable
    fun status(signIn: () -> Unit, signInLabel: String = "sign in to continue") {
        val problem = error
        if (problem != null) {
            val message = if (problem == "sign in") signInLabel else problem
            Column(Modifier.padding(horizontal = 20.dp)) {
                BodyStatus(message + (checked?.let { " · last checked ${formattedTime(it.toString())}" } ?: ""))
                if (problem == "sign in") TextButton(onClick = signIn) { Text("sign in") }
                else if (problem != UpdateViewerMessage) TextButton(onClick = { attempt++ }) { Text("retry") }
            }
        } else if (!received) CircularProgressIndicator(Modifier.padding(20.dp))
    }
}

@Composable
internal fun <T> Read(
    key: Any,
    reload: Pair<Int, Int>,
    signIn: () -> Unit,
    load: suspend () -> T?,
    signInLabel: String = "sign in to continue",
    content: @Composable (T?) -> Unit,
) {
    val state = remember(key) { ReadState<T>() }
    state.load(key, reload, load)
    state.status(signIn, signInLabel)
    if (state.received) content(state.data)
}

internal fun formattedTime(value: String?, timezone: String? = null): String {
    if (value == null) return ""
    val zone = timezone?.let(ZoneId::of) ?: ZoneId.systemDefault()
    return DateTimeFormatter.ofPattern("MMM d, h:mm a${if (timezone != null) " z" else ""}", Locale.getDefault())
        .withZone(zone).format(Instant.parse(value))
}

internal fun civilDate(value: String): String =
    LocalDate.parse(value).format(DateTimeFormatter.ofPattern("MMM d", Locale.getDefault()))

private val LinkStart = Regex(
    """\[([^\]\n]+)]\((?=https?://|/)|attachment:([0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12})|https?://[^\s<>]+|(?<![\w/])/(?:[mft]/|mail/|files\b|artifacts\b|todos\b)[^\s<>]*""",
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
