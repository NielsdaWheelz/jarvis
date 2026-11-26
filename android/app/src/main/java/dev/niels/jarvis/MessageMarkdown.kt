package dev.niels.jarvis

import android.content.ActivityNotFoundException
import android.content.Intent
import android.net.Uri
import android.widget.Toast
import androidx.compose.foundation.focusGroup
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusDirection
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalInputModeManager
import androidx.compose.ui.input.InputMode
import androidx.compose.ui.input.InputModeManager
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.semantics.CollectionInfo
import androidx.compose.ui.semantics.CollectionItemInfo
import androidx.compose.ui.semantics.collectionInfo
import androidx.compose.ui.semantics.collectionItemInfo
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.*
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp
import org.commonmark.ext.gfm.tables.*
import org.commonmark.node.*
import org.commonmark.node.Text as MdText
import org.json.JSONObject

private val bare = Regex("""https?://[^\s<>]+|/(?:[mft]/|mail/|files\b|artifacts\b|todos\b)[^\s<>]*|attachment:[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}""", RegexOption.IGNORE_CASE)

private class Reader(val message: JSONObject?, val navigate: (Route) -> Unit, val external: (Uri) -> Unit) {
    fun destination(href: String): (() -> Unit)? {
        if (href.startsWith("//") || href.any { it <= ' ' || it == '\\' }) return null
        val uri = Uri.parse(href).normalizeScheme()
        val origin = Uri.parse(Routes.origin)
        val authority = uri.encodedAuthority
        val internal = uri.scheme == origin.scheme && (authority.equals(origin.encodedAuthority, true) ||
            authority.equals("${origin.encodedAuthority}:443", true))
        if (href.startsWith("/") || internal) {
            val route = if (internal) Routes.parse(uri.buildUpon().encodedAuthority(origin.encodedAuthority).build()) else hrefRoute(href)
            if (route == null) return null
            if (route is Route.Source || route is Route.Table) return null
            return { navigate(route) }
        }
        if (uri.scheme !in setOf("http", "https") || uri.host.isNullOrBlank() || uri.userInfo != null) return null
        return { external(uri) }
    }
}

@Composable
private fun reader(message: JSONObject?, navigate: (Route) -> Unit, onExternal: () -> Unit = {}): Reader {
    val context = LocalContext.current
    return Reader(message, navigate) { uri ->
        onExternal()
        try { context.startActivity(Intent(Intent.ACTION_VIEW, uri)) }
        catch (_: ActivityNotFoundException) { Toast.makeText(context, "browser unavailable", Toast.LENGTH_SHORT).show() }
    }
}

@Composable
internal fun MessageMarkdown(message: JSONObject, navigate: (Route) -> Unit, onExternal: () -> Unit) {
    val text = message.getString("text")
    val markdown = remember(text) { MessageDocument(text) }
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        MarkdownBlocks(markdown.root, markdown, reader(message, navigate, onExternal))
        val present = message.optJSONObject("present")?.optJSONObject("ref")
        if (present?.string("kind") == "source") {
            val slot = present.optInt("slot")
            val meta = message.objects("sources").find { it.optInt("slot") == slot }
            if (slot !in markdown.markers && meta != null) {
                if (meta.string("state") == "available") {
                    TextButton(onClick = { navigate(Route.Source(message.getString("id"), slot)) }) {
                        Text(if (meta.string("kind") == "event") "open cited event" else "open cited email")
                    }
                } else BodyStatus("source unavailable")
            }
        }
    }
}

@Composable
internal fun TablePane(route: Route.Table, api: HomeApi, reload: Pair<Int, Int>, signIn: () -> Unit, navigate: (Route) -> Unit, back: (() -> Unit)?) {
    val path = "/api/messages/${route.message}"
    Read(path, reload, signIn, { api.read(path) }) { message ->
        Pane {
            val markdown = message?.getString("text")?.let { remember(it) { MessageDocument(it) } }
            val table = markdown?.tables?.entries?.find { it.value == (route.ordinal to route.digest) }?.key
            if (table == null) BodyStatus("table unavailable")
            else {
                Heading("table ${route.ordinal}")
                MarkdownTable(table, null, reader(message, navigate))
            }
            if (back == null) TextButton(onClick = { navigate(Route.Message(route.message)) }) { Text("back to message") }
        }
    }
}

@Composable
private fun MarkdownBlocks(parent: Node, markdown: MessageDocument, reader: Reader) {
    parent.children.forEach { node ->
        when (node) {
            is org.commonmark.node.Paragraph -> Inline(node, reader)
            is Heading -> {
                val style = when (node.level) {
                    1 -> MaterialTheme.typography.titleLarge
                    2 -> MaterialTheme.typography.titleMedium
                    else -> MaterialTheme.typography.titleSmall
                }
                Inline(node, reader, Modifier.semantics { heading() }, style)
            }
            is TableBlock -> {
                val (number, digest) = markdown.tables.getValue(node)
                MarkdownTable(node, reader.message?.let { Route.Table(it.getString("id"), number, digest) }, reader)
            }
            is BlockQuote -> Column(Modifier.padding(start = 12.dp)) { MarkdownBlocks(node, markdown, reader) }
            is BulletList, is OrderedList -> node.children.forEachIndexed { i, item ->
                Row {
                    Text(if (node is OrderedList) "${(node.markerStartNumber ?: 1) + i}. " else "• ")
                    Column(Modifier.weight(1f)) { MarkdownBlocks(item, markdown, reader) }
                }
            }
            is ThematicBreak -> HorizontalDivider()
            is HtmlBlock -> SelectionContainer { Text(node.literal) }
            is FencedCodeBlock -> CodeBlock(node.literal)
            is IndentedCodeBlock -> CodeBlock(node.literal)
        }
    }
}

@Composable
private fun CodeBlock(text: String) {
    SelectionContainer { Text(text.removeSuffix("\n"), Modifier.horizontalScroll(rememberScrollState()), fontFamily = FontFamily.Monospace) }
}

@Composable
private fun MarkdownTable(table: TableBlock, expand: Route.Table?, reader: Reader) {
    val rows = table.children.flatMap { it.children }.map { it.children.filterIsInstance<TableCell>().toList() }.toList()
    val measurer = rememberTextMeasurer()
    val density = LocalDensity.current
    val style = MaterialTheme.typography.bodyMedium
    val widths = (0 until (rows.maxOfOrNull { it.size } ?: 0)).map { col ->
        val pixels = rows.maxOf { row ->
            val cell = row.getOrNull(col)
            if (cell == null) 0 else measurer.measure(plainText(cell), style.copy(fontWeight = if (cell.isHeader) FontWeight.Bold else FontWeight.Normal), softWrap = false).size.width
        }
        with(density) { pixels.toDp().coerceAtMost(320.dp) + 20.dp }
    }
    val scroll = rememberScrollState()
    val focus = remember { FocusRequester() }
    val inputMode = LocalInputModeManager.current
    var returning by rememberSaveable { mutableStateOf(false) }
    val restore = remember { returning }
    Column {
        Column(Modifier.horizontalScroll(scroll).semantics { collectionInfo = CollectionInfo(rows.size, widths.size) }) {
            rows.forEachIndexed { rowIndex, row ->
                Row {
                    row.forEachIndexed { col, cell ->
                        val cellStyle = if (cell.isHeader) style.copy(fontWeight = FontWeight.Bold) else style
                        val cellModifier = Modifier.width(widths[col]).padding(horizontal = 8.dp, vertical = 3.dp).semantics {
                            collectionItemInfo = CollectionItemInfo(rowIndex, 1, col, 1)
                            if (cell.isHeader) heading()
                        }
                        Inline(cell, reader, cellModifier, cellStyle)
                    }
                }
                HorizontalDivider()
            }
        }
        if (expand != null && scroll.maxValue != Int.MAX_VALUE && scroll.maxValue > 0) {
            TextButton(onClick = {
                returning = true
                reader.navigate(expand)
            }, modifier = Modifier.focusRequester(focus)) {
                Text("expand table")
            }
            LaunchedEffect(restore) {
                if (restore) {
                    focus.restoreAfterNavigation(inputMode)
                    returning = false
                }
            }
        }
    }
}

private fun plainText(node: Node): String = when (node) {
    is MdText -> node.literal
    is Code -> node.literal
    is HtmlInline -> node.literal
    is SoftLineBreak, is HardLineBreak -> "\n"
    else -> node.children.joinToString("") { plainText(it) }
}

@Composable
internal fun LinkedText(text: String, navigate: (Route) -> Unit) = Inline(MdText(text), reader(null, navigate))

@Composable
private fun Inline(node: Node, reader: Reader, modifier: Modifier = Modifier, style: TextStyle = LocalTextStyle.current) {
    val colors = TextLinkStyles(style = SpanStyle(color = MaterialTheme.colorScheme.primary, textDecoration = TextDecoration.Underline))
    val requester = remember { FocusRequester() }
    val manager = LocalFocusManager.current
    val inputMode = LocalInputModeManager.current
    var lastLink by rememberSaveable { mutableIntStateOf(-1) }
    val restoreLink = remember { lastLink }
    val body = buildAnnotatedString {
        var next = 0
        fun link(href: String, action: () -> Unit, label: AnnotatedString.Builder.() -> Unit) {
            val index = next++
            withLink(LinkAnnotation.Clickable("$index:$href", colors) {
                lastLink = index
                action()
            }, label)
        }
        fun literal(value: String) {
            var end = 0
            for (match in bare.findAll(value)) {
                val previous = value.getOrNull(match.range.first - 1)
                if (previous != null && (previous.isLetterOrDigit() || previous in "_:/")) continue
                var href = match.value.trimEnd('.', ',', ';', ':', '!', '?', '\'', '"', ']', '}', '”', '’')
                while (href.endsWith(")") && href.count { it == ')' } > href.count { it == '(' }) href = href.dropLast(1)
                val attachment = href.startsWith("attachment:", ignoreCase = true)
                val action = reader.destination(if (attachment) "/f/" + href.substringAfter(':') else href) ?: continue
                append(value.substring(end, match.range.first))
                link(href, action) { append(if (attachment) "original file" else href) }
                end = match.range.first + href.length
            }
            append(value.substring(end))
        }
        fun inline(n: Node, scan: Boolean) {
            fun contents(scanChildren: Boolean = scan) = n.children.forEach { inline(it, scanChildren) }
            when (n) {
                is MdText -> if (scan) literal(n.literal) else append(n.literal)
                is Code -> withStyle(SpanStyle(fontFamily = FontFamily.Monospace)) { append(n.literal) }
                is Emphasis -> withStyle(SpanStyle(fontStyle = FontStyle.Italic)) { contents() }
                is StrongEmphasis -> withStyle(SpanStyle(fontWeight = FontWeight.Bold)) { contents() }
                is HardLineBreak, is SoftLineBreak -> append("\n")
                is HtmlInline -> append(n.literal)
                is Image -> append(plainText(n))
                is Link -> {
                    val marker = sourceMarker.matchEntire(n.destination)
                    val msg = reader.message
                    if (marker != null && msg?.string("role") == "assistant" && msg.optJSONArray("sources") != null) {
                        val slot = marker.groupValues[1].toIntOrNull()
                        val bound = msg.objects("sources").any { it.optInt("slot") == slot && it.string("state") == "available" }
                        if (slot != null && bound) link(n.destination, { reader.navigate(Route.Source(msg.getString("id"), slot)) }) { contents(false) }
                        else {
                            contents(false)
                            append(" (source unavailable)")
                        }
                    } else {
                        val action = reader.destination(n.destination)
                        if (action == null) contents(false) else link(n.destination, action) { contents(false) }
                    }
                }
                else -> contents()
            }
        }
        inline(node, true)
    }
    val hasLinks = body.getLinkAnnotations(0, body.length).isNotEmpty()
    val content = @Composable { Text(body, modifier.focusRequester(requester).focusGroup(), style = style) }
    if (hasLinks) content() else SelectionContainer(content = content)
    LaunchedEffect(restoreLink) {
        if (restoreLink >= 0 && body.getLinkAnnotations(0, body.length).size > restoreLink) {
            if (!requester.restoreAfterNavigation(inputMode)) return@LaunchedEffect
            repeat(restoreLink) { manager.moveFocus(FocusDirection.Next) }
            lastLink = -1
        }
    }
}

// Android's link targets become keyboard-focusable after the touch mode transition.
private suspend fun FocusRequester.restoreAfterNavigation(input: InputModeManager): Boolean {
    input.requestInputMode(InputMode.Keyboard)
    withFrameNanos { }
    return requestFocus()
}
