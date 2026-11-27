package dev.niels.jarvis

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.saveable.rememberSaveableStateHolder
import androidx.compose.runtime.setValue
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import java.io.IOException
import kotlinx.coroutines.flow.MutableStateFlow

internal class HomeVisits : ViewModel() {
    val todos = mutableMapOf<String, TodoReads>()
    private var chat: ChatHistory? = null

    fun chat(shown: ChatShown) = chat ?: ChatHistory(shown).also { chat = it }
}

class MainActivity : ComponentActivity() {
    private val destination = MutableStateFlow<Intent?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val initial = intent.data?.let(Routes::parse) ?: Route.Home
        val visits = ViewModelProvider(this)[HomeVisits::class.java]
        val notices = PhoneNotices.get(this)
        notices.foreground(false)
        val chat = visits.chat(notices.shown)
        setContent {
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
            val api = remember { HomeApi(this@MainActivity) }
            val drafts = remember { Drafts.get(this@MainActivity) }
            val authRevision by access.revision.collectAsState()
            val presence = remember(authRevision) { Presence { drafts.locked } }
            val haptic = LocalHapticFeedback.current
            val accept by rememberUpdatedState<(ChatMessage) -> Unit>({ row ->
                chat.accept(row)
                presence.accepted()
                haptic.performHapticFeedback(HapticFeedbackType.Confirm)
            })
            val readPage: suspend (String?, Long?) -> ChatPage = remember(api, notices, drafts) {
                { before, timeout ->
                    readChatPage(api, notices, before, timeout) { drafts.checkReceipt(api) { accept(it) } }
                }
            }
            ObservePresence(api, presence, chat, readPage)
            LaunchedEffect(drafts.draft?.held, drafts.sending, authRevision) {
                if (drafts.draft?.held == true && !drafts.sending) {
                    try {
                        drafts.checkReceipt(api, accept)
                    } catch (_: IOException) {
                        // The held draft remains actionable while the receipt is unavailable.
                    }
                }
            }
            var openDock by rememberSaveable { mutableStateOf(intent.getBooleanExtra("chat", false)) }

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
                incoming?.let { request ->
                    request.data?.let(Routes::parse)?.let(::navigate)
                    if (request.getBooleanExtra("chat", false)) openDock = true
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
                    drafts = drafts, readPage = { readPage(it, null) }, accept = accept,
                    openDock = openDock, dockOpened = { openDock = false },
                )
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        destination.value = intent
    }
}
