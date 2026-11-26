package dev.niels.jarvis

import org.commonmark.ext.gfm.tables.TableBlock
import org.commonmark.ext.gfm.tables.TablesExtension
import org.commonmark.ext.gfm.tables.internal.TableBlockParser
import org.commonmark.internal.BlockStartImpl
import org.commonmark.node.Image
import org.commonmark.node.Link
import org.commonmark.node.Node
import org.commonmark.parser.IncludeSourceSpans
import org.commonmark.parser.Parser
import org.commonmark.parser.block.BlockContinue
import org.commonmark.parser.block.BlockParser
import org.commonmark.parser.block.BlockStart
import org.commonmark.parser.block.ParserState
import java.security.MessageDigest

internal val sourceMarker = Regex("#source-([1-9][0-9]*)")

// Retain the pinned extension's cell parser. Let CommonMark decide when another block
// interrupts a table, even when that new heading, fence or quotation contains a pipe.
private val gfmTables = TableBlockParser.Factory(TablesExtension.DEFAULT_MAX_CELLS)
private val parser = Parser.builder().customBlockParserFactory { state, matched ->
    val start = gfmTables.tryStart(state, matched) as? BlockStartImpl
        ?: return@customBlockParserFactory BlockStart.none()
    val header = matched.paragraphLines.lines.last().content.toString()
    val delimiter = state.line.content.subSequence(state.index, state.line.content.length).toString()
    if (columnCount(header) != columnCount(delimiter)) return@customBlockParserFactory BlockStart.none()
    val cells = start.blockParsers.single()
    val table = object : BlockParser by cells {
        var continues = true
        override fun canHaveLazyContinuationLines() = continues
        override fun tryContinue(state: ParserState): BlockContinue? {
            val content = state.line.content
            continues = content.subSequence(state.nextNonSpaceIndex, content.length).trimEnd() != "|"
            return BlockContinue.none()
        }
    }
    BlockStart.of(table).atIndex(state.index).replaceParagraphLines(1)
}.includeSourceSpans(IncludeSourceSpans.BLOCKS_AND_INLINES).build()

private fun columnCount(line: String): Int {
    val row = line.trim().removePrefix("|")
    var count = 0
    for (i in row.indices) if (row[i] == '|' && row.getOrNull(i - 1) != '\\') count++
    return if (row.endsWith('|') && row.getOrNull(row.lastIndex - 1) != '\\') count else count + 1
}
internal val Node.children: Sequence<Node> get() = generateSequence(firstChild) { it.next }

internal class MessageDocument(text: String) {
    val markers = mutableSetOf<Int>()
    val root: Node
    val tables = linkedMapOf<TableBlock, Pair<Int, String>>()
    init {
        val normalized = text.replace("\r\n", "\n").replace('\r', '\n')
        root = parser.parse(normalized)
        val lines = normalized.split('\n')
        fun index(node: Node) {
            if (node is Image) return
            if (node is Link) sourceMarker.matchEntire(node.destination)?.groupValues?.get(1)?.toIntOrNull()?.let(markers::add)
            if (node is TableBlock) {
                val spans = node.sourceSpans
                val source = lines.subList(spans.first().lineIndex, spans.last().lineIndex + 1).joinToString("\n")
                val hash = MessageDigest.getInstance("SHA-256").digest(source.toByteArray())
                tables[node] = tables.size + 1 to hash.joinToString("") { "%02x".format(it) }
            }
            node.children.forEach(::index)
        }
        index(root)
    }
}
