package dev.niels.jarvis

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.saveable.rememberSaveableStateHolder
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import kotlinx.coroutines.flow.MutableStateFlow

internal class TodoVisits : ViewModel() {
    val reads = mutableMapOf<String, TodoReads>()
}

class MainActivity : ComponentActivity() {
    private val destination = MutableStateFlow<Uri?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val initial = intent.data?.let(Routes::parse) ?: Route.Home
        val todoReads = ViewModelProvider(this)[TodoVisits::class.java].reads
        setContent {
            val start = Routes.url(initial).toString()
            var trail by rememberSaveable { mutableStateOf(arrayListOf(start)) }
            val holder = rememberSaveableStateHolder()
            val incoming by destination.collectAsState()

            // a repeated address is a new visit. back restores the actual origin.
            val visit = "${trail.lastIndex} ${trail.last()}"
            fun discardVisit() {
                holder.removeState(visit)
                todoReads.remove(visit)
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
                discardVisit()
                trail = ArrayList(trail.dropLast(1) + Routes.url(route).toString())
            }

            fun back() {
                if (trail.size > 1) {
                    discardVisit()
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
                    entry = Routes.parse(Uri.parse(trail.last())) ?: Route.Home,
                    onNavigate = ::navigate, onResolve = ::resolve,
                    todoReads = { todoReads.getOrPut(visit, ::TodoReads) },
                    onBack = if (trail.size > 1) ::back else null
                )
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        destination.value = intent.data
    }
}
