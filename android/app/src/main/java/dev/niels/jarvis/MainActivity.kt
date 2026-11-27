package dev.niels.jarvis

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.saveable.rememberSaveableStateHolder
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshotFlow
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.first

internal class HomeVisits : ViewModel() {
    val todos = mutableMapOf<String, TodoReads>()
    private var chat: ChatHistory? = null

    fun chat(api: HomeApi, reports: ShownReports, notices: PhoneNotices) =
        chat ?: ChatHistory(api, reports, notices).also { chat = it }
}

class MainActivity : ComponentActivity() {
    private val destination = MutableStateFlow<Uri?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val initial = intent.data?.let(Routes::parse) ?: Route.Home
        val visits = ViewModelProvider(this)[HomeVisits::class.java]
        val notices = PhoneNotices.get(this)
        val opening = notices.foreground(false)
        val api = HomeApi(applicationContext)
        val reports = ShownReports.get(applicationContext)
        val chat = visits.chat(api, reports, notices)
        setContent {
            LaunchedEffect(chat, notices) {
                snapshotFlow { chat.latest.settled }.first { it }
                notices.releaseHeld(opening)
            }
            val start = Routes.url(initial).toString()
            var trail by rememberSaveable {
                val visits = arrayListOf<String>()
                if (initial is Route.Artifact) visits.add(Routes.url(Route.Artifacts).toString())
                visits.add(start)
                mutableStateOf(visits)
            }
            val holder = rememberSaveableStateHolder()
            val incoming by destination.collectAsState()
            val access = remember { Access.get(this@MainActivity) }
            val authRevision by access.revision.collectAsState()
            val presence = rememberPresence(api, authRevision, chat, notices)

            // a repeated address is a new visit. back restores the actual origin.
            val depth = trail.lastIndex
            val address = trail.last()
            val visit = "$depth $address"
            // A custom tab may have checkpointed this active visit. Drop its saved
            // snapshot after the provider leaves composition if the stack removed it.
            DisposableEffect(visit) {
                onDispose {
                    if (trail.getOrNull(depth) != address) {
                        holder.removeState(visit)
                        visits.todos.remove(visit)
                    }
                }
            }

            fun navigate(route: Route) {
                if (route is Route.Mail) {
                    if (!Routes.openInBrowser(this, route)) {
                        Toast.makeText(this, "could not open this draft in a browser", Toast.LENGTH_LONG).show()
                    }
                    return
                }
                trail = ArrayList(trail + Routes.url(route).toString())
            }

            fun resolve(route: Route) {
                trail = ArrayList(trail.dropLast(1) + Routes.url(route).toString())
            }

            fun back() {
                if (trail.size > 1) {
                    trail = ArrayList(trail.dropLast(1))
                }
            }

            LaunchedEffect(incoming) {
                incoming?.let { uri ->
                    Routes.parse(uri)?.let(::navigate)
                    destination.value = null
                }
            }
            BackHandler(enabled = trail.size > 1, onBack = ::back)
            holder.SaveableStateProvider(visit) {
                JarvisHome(
                    entry = Routes.parse(Uri.parse(address)) ?: Route.Home,
                    onNavigate = ::navigate, onResolve = ::resolve,
                    todoReads = { visits.todos.getOrPut(visit, ::TodoReads) },
                    history = chat, notices = notices,
                    onBack = if (trail.size > 1) ::back else null,
                    api = api, authRevision = authRevision, presence = presence,
                )
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        destination.value = intent.data
    }
}
