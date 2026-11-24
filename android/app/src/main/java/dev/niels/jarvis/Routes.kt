package dev.niels.jarvis

import android.app.Activity
import android.content.ActivityNotFoundException
import android.net.Uri
import androidx.browser.customtabs.CustomTabsIntent
import net.openid.appauth.browser.BrowserSelector

internal sealed interface Route {
    data object Home : Route
    data object Overview : Route
    data class Message(val id: String) : Route
    data class Todo(val id: String) : Route
    data class File(val id: String, val page: Long?) : Route
    data class Canvas(val slug: String, val revision: String?) : Route
}

internal object Routes {
    const val origin = BuildConfig.JARVIS_ORIGIN
    private val originUri = Uri.parse(origin)
    private val uuid = Regex("[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
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
                "/overview" -> return Route.Overview
            }
        }
        val segments = path.removePrefix("/").split('/')
        val name = segments.getOrNull(1) ?: return null
        if (segments[0] == "v") {
            if (query != null || segments.size > 3 || name.length > 64 || !slug.matches(name)) {
                return null
            }
            val rev = segments.getOrNull(2)
            return if (rev == null || revision.matches(rev)) Route.Canvas(name, rev) else null
        }
        if (segments.size != 2 || !uuid.matches(name)) return null
        return when (segments[0]) {
            "m" -> if (query == null) Route.Message(name) else null
            "t" -> if (query == null) Route.Todo(name) else null
            "f" -> {
                if (query == null) return Route.File(name, null)
                val page = pageQuery.matchEntire(query)?.groupValues?.get(1)?.toLongOrNull()
                if (page != null && page <= maxPage) Route.File(name, page) else null
            }
            else -> null
        }
    }

    fun url(route: Route): Uri = originUri.buildUpon().apply {
        when (route) {
            Route.Home -> path("/")
            Route.Overview -> appendPath("overview")
            is Route.Message -> appendPath("m").appendPath(route.id)
            is Route.Todo -> appendPath("t").appendPath(route.id)
            is Route.File -> {
                appendPath("f").appendPath(route.id)
                route.page?.let { appendQueryParameter("page", it.toString()) }
            }
            is Route.Canvas -> {
                appendPath("v").appendPath(route.slug)
                route.revision?.let { appendPath(it) }
            }
        }
    }.build()

    fun openCanvas(activity: Activity, route: Route.Canvas): Boolean {
        if (route.revision == null) return false
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
