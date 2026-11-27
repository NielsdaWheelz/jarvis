package dev.niels.jarvis

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.material3.TextButton
import androidx.compose.material3.Text
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import java.io.IOException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

class ShareActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val capture = ViewModelProvider(this)[ShareCapture::class.java]
        capture.receive(Drafts.get(this), intent)
        setContent {
            val state by capture.state.collectAsState()
            JarvisPaper {
                Column(Modifier.windowInsetsPadding(WindowInsets.safeDrawing).padding(20.dp)) {
                    when (val result = state) {
                        CaptureState.Copying -> BodyStatus("copying the shared original")
                        is CaptureState.Unavailable -> {
                            BodyStatus(result.message)
                            TextButton(onClick = ::finish) { Text("return") }
                        }
                        CaptureState.Saved -> LaunchedEffect(Unit) {
                            startActivity(Intent(this@ShareActivity, MainActivity::class.java)
                                .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP)
                                .putExtra("chat", true))
                            finish()
                        }
                    }
                }
            }
        }
    }
}

internal sealed interface CaptureState {
    data object Copying : CaptureState
    data object Saved : CaptureState
    data class Unavailable(val message: String) : CaptureState
}

internal class ShareCapture : ViewModel() {
    private var started = false
    private val result = MutableStateFlow<CaptureState>(CaptureState.Copying)
    val state: StateFlow<CaptureState> get() = result

    fun receive(drafts: Drafts, intent: Intent) {
        if (started) return
        started = true
        viewModelScope.launch {
            result.value = try {
                drafts.receive(intent)
                CaptureState.Saved
            } catch (e: DraftProblem) {
                CaptureState.Unavailable(checkNotNull(e.message))
            } catch (_: IOException) {
                CaptureState.Unavailable("could not save this share. try sharing it again.")
            } catch (_: SecurityException) {
                CaptureState.Unavailable("could not read this share. try sharing it again.")
            }
        }
    }
}
