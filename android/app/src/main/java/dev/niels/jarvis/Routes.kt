package dev.niels.jarvis

import android.app.Activity
import android.content.ActivityNotFoundException
import android.net.Uri
import androidx.browser.customtabs.CustomTabsIntent
import net.openid.appauth.browser.BrowserSelector

internal sealed interface Route {
    data object Home : Route
    data object Artifacts : Route
    data object Todos : Route
    data object Files : Route
    data class Message(val id: String) : Route
    data class Source(val reply: String, val slot: Int) : Route
    data class Table(val message: String, val ordinal: Int, val digest: String) : Route
    data class Mail(val messageId: String, val actionId: String, val historical: Boolean) : Route
    data class Todo(val id: String) : Route
    data class File(val id: String, val page: Long?) : Route
    data class DriveFile(val subject: String, val id: String, val page: Long? = null) : Route
    data class Artifact(val slug: String, val revision: String?) : Route
}

internal object Routes {
    const val origin = BuildConfig.JARVIS_ORIGIN
    private val originUri = Uri.parse(origin)
    private val uuid = Regex("[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
    private val driveId = Regex("[A-Za-z0-9_-]{1,255}")
    private val slug = Regex("[a-z0-9]+(?:-[a-z0-9]+)*")
    private val revision = Regex("[0-9a-f]{40}|[0-9a-f]{64}")
    private val pageQuery = Regex("page=([1-9][0-9]{0,15})")
    private const val maxPage = 9_007_199_254_740_991L

    fun parse(uri: Uri): Route? {
        if (uri.scheme != originUri.scheme || uri.encodedAuthority != originUri.encodedAuthority ||
            uri.encodedFragment != null
        ) return null

        val path = uri.encodedPath.orEmpty()
        val query = uri.encodedQuery
        if (query == null) {
            when (path) {
                "", "/" -> return Route.Home
                "/todos" -> return Route.Todos
                "/artifacts" -> return Route.Artifacts
                "/files" -> return Route.Files
            }
        }
        val segments = path.removePrefix("/").split('/')
        val name = segments.getOrNull(1) ?: return null
        if (segments[0] == "m" && segments.size >= 4 && uuid.matches(name) && query == null) {
            val ordinal = segments[3].toIntOrNull()?.takeIf { it > 0 && it.toString() == segments[3] } ?: return null
            return when {
                segments[2] == "source" && segments.size == 4 -> Route.Source(name, ordinal)
                segments[2] == "table" && segments.size == 5 && Regex("[0-9a-f]{64}").matches(segments[4]) ->
                    Route.Table(name, ordinal, segments[4])
                else -> null
            }
        }
        if (segments[0] == "mail") {
            if (query != null || segments.size != 4 || segments[2] !in setOf("draft", "revision") ||
                !uuid.matches(name) || !uuid.matches(segments[3])) return null
            return Route.Mail(name, segments[3], historical = segments[2] == "revision")
        }
        if (segments[0] == "artifacts") {
            if (query != null || segments.size > 3 || name.length > 64 || !slug.matches(name)) {
                return null
            }
            val rev = segments.getOrNull(2)
            return if (rev == null || revision.matches(rev)) Route.Artifact(name, rev) else null
        }
        val page = query?.let {
            pageQuery.matchEntire(it)?.groupValues?.get(1)?.toLongOrNull()?.takeIf { it <= maxPage }
        }
        if (segments[0] == "files") {
            val id = segments.getOrNull(2) ?: return null
            if (segments.size != 3 || !driveId.matches(name) || !driveId.matches(id) ||
                (query != null && page == null)
            ) return null
            return Route.DriveFile(name, id, page)
        }
        if (segments.size != 2 || !uuid.matches(name)) return null
        return when (segments[0]) {
            "m" -> if (query == null) Route.Message(name) else null
            "t" -> if (query == null) Route.Todo(name) else null
            "f" -> if (query == null || page != null) Route.File(name, page) else null
            else -> null
        }
    }

    fun url(route: Route): Uri = originUri.buildUpon().apply {
        when (route) {
            Route.Home -> path("/")
            Route.Todos -> appendPath("todos")
            Route.Artifacts -> appendPath("artifacts")
            Route.Files -> appendPath("files")
            is Route.Message -> appendPath("m").appendPath(route.id)
            is Route.Source -> appendPath("m").appendPath(route.reply).appendPath("source").appendPath(route.slot.toString())
            is Route.Table -> appendPath("m").appendPath(route.message).appendPath("table").appendPath(route.ordinal.toString()).appendPath(route.digest)
            is Route.Mail -> appendPath("mail").appendPath(route.messageId)
                .appendPath(if (route.historical) "revision" else "draft").appendPath(route.actionId)
            is Route.Todo -> appendPath("t").appendPath(route.id)
            is Route.File -> {
                appendPath("f").appendPath(route.id)
                route.page?.let { appendQueryParameter("page", it.toString()) }
            }
            is Route.DriveFile -> {
                appendPath("files").appendPath(route.subject).appendPath(route.id)
                route.page?.let { appendQueryParameter("page", it.toString()) }
            }
            is Route.Artifact -> {
                appendPath("artifacts").appendPath(route.slug)
                route.revision?.let { appendPath(it) }
            }
        }
    }.build()

    fun openInBrowser(activity: Activity, route: Route): Boolean {
        if (route !is Route.Mail && !(route is Route.Artifact && route.revision != null)) return false
        val destination = url(route)
        if (parse(destination) != route) return false
        val browser = BrowserSelector.select(activity) { it.useCustomTab } ?: return false
        val tab = CustomTabsIntent.Builder().setSendToExternalDefaultHandlerEnabled(false).build()
        tab.intent.setPackage(browser.packageName)
        return try {
            tab.launchUrl(activity, destination)
            true
        } catch (_: ActivityNotFoundException) {
            false
        }
    }
}
