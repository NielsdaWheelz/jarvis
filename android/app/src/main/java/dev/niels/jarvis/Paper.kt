package dev.niels.jarvis

import androidx.compose.foundation.clickable
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.sizeIn
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.ExperimentalTextApi
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontSynthesis
import androidx.compose.ui.text.font.FontVariation
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.Hyphens
import androidx.compose.ui.text.style.LineBreak
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.em
import androidx.compose.ui.unit.sp

private val LightSurface = Color(0xFFFBFAF6)
private val DarkSurface = Color(0xFF20221F)
private val LightInk = Color(0xFF252621)
private val DarkInk = Color(0xFFF3F2E8)
private val LightLine = Color(0xFFD8D9CE)
private val DarkLine = Color(0xFF42453E)

@Composable
internal fun rubric() = if (isSystemInDarkTheme()) Color(0xFFEE9A83) else Color(0xFFA33B25)

@Composable
internal fun JarvisPaper(
    modifier: Modifier = Modifier.fillMaxSize(),
    content: @Composable () -> Unit,
) {
    val dark = isSystemInDarkTheme()
    val colors = if (dark) darkColorScheme(
        background = Color(0xFF191B19), surface = DarkSurface, onSurface = DarkInk,
        onBackground = DarkInk, primary = Color(0xFFB5CBB7), onPrimary = Color(0xFF1C3524),
        onSurfaceVariant = Color(0xFFACAFA5), outline = Color(0xFF777C73), outlineVariant = DarkLine,
        surfaceContainerLowest = DarkSurface, surfaceContainerLow = DarkSurface, surfaceContainer = DarkSurface,
        surfaceContainerHigh = DarkSurface, surfaceContainerHighest = DarkSurface, error = DarkInk,
    ) else lightColorScheme(
        background = Color(0xFFF4F2EC), surface = LightSurface, onSurface = LightInk,
        onBackground = LightInk, primary = Color(0xFF43564A), onPrimary = Color.White,
        onSurfaceVariant = Color(0xFF64675F), outline = Color(0xFF777C73), outlineVariant = LightLine,
        surfaceContainerLowest = LightSurface, surfaceContainerLow = LightSurface, surfaceContainer = LightSurface,
        surfaceContainerHigh = LightSurface, surfaceContainerHighest = LightSurface, error = LightInk,
    )
    val type = Typography()
    MaterialTheme(colorScheme = colors, typography = type.copy(
        headlineLarge = type.headlineLarge.copy(fontFamily = FontFamily.Serif),
        headlineSmall = type.headlineSmall.copy(fontFamily = FontFamily.Serif),
    )) {
        Surface(modifier, color = colors.background, contentColor = colors.onBackground, content = content)
    }
}

@OptIn(ExperimentalTextApi::class)
private fun literata(size: TextUnit) = FontFamily(
    listOf(380, 400, 600).flatMap { weight ->
        listOf(
            R.font.literata_3_103_roman to FontStyle.Normal,
            R.font.literata_3_103_italic to FontStyle.Italic,
        ).map { (resource, style) ->
            Font(resource, FontWeight(weight), style, variationSettings = FontVariation.Settings(
                FontVariation.weight(weight), FontVariation.opticalSizing(size),
            ))
        }
    },
)

internal val ChatDisplay = FontFamily(
    Font(R.font.cormorant_garamond_regular),
    Font(R.font.cormorant_garamond_italic, style = FontStyle.Italic),
)
internal val ChatBodySize = 17.sp
private val BodyFace = literata(ChatBodySize)
private val ApparatusFace = literata(15.sp)
private val SmallFace = literata(12.sp)

@Composable
internal fun chatBody(owner: Boolean = false, progress: Boolean = false) = TextStyle(
    fontFamily = if (progress) ApparatusFace else BodyFace,
    fontSize = if (progress) 15.sp else ChatBodySize,
    lineHeight = 1.5.em,
    fontWeight = FontWeight(if (isSystemInDarkTheme()) 380 else 400),
    fontStyle = if (owner) FontStyle.Italic else FontStyle.Normal,
    fontSynthesis = FontSynthesis.None,
    lineBreak = if (owner) LineBreak.Simple else LineBreak.Paragraph,
    hyphens = if (owner) Hyphens.None else Hyphens.Auto,
    fontFeatureSettings = "onum",
)

internal val ChatApparatus = TextStyle(
    fontFamily = ApparatusFace, fontSize = 15.sp, lineHeight = 1.5.em, fontSynthesis = FontSynthesis.None,
)

internal val ChatCaps = TextStyle(
    fontFamily = SmallFace, fontSize = 12.sp, lineHeight = 1.4.em, fontSynthesis = FontSynthesis.None,
    fontFeatureSettings = "smcp, c2sc", letterSpacing = .06.em,
)

internal val ChatMurmur = TextStyle(
    fontFamily = ChatDisplay, fontSize = 18.sp, lineHeight = 1.25.em, fontStyle = FontStyle.Italic,
)

@Composable
internal fun MessageStamp(speaker: String, time: String, owed: Boolean = false, fresh: Boolean = false, timeAlpha: Float = 1f) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.weight(1f)) {
            if (owed) Text("needs a reply", color = rubric(), style = ChatCaps)
        }
        Text(time.ifEmpty { " " }, Modifier.clearAndSetSemantics {
            contentDescription = listOfNotNull("new".takeIf { fresh }, speaker, time.takeIf(String::isNotEmpty)).joinToString(" · ")
        }, color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = timeAlpha), style = ChatCaps.copy(
            fontFeatureSettings = "onum, tnum", letterSpacing = .04.em,
        ))
    }
}

@Composable
internal fun ChatWord(
    text: String, onClick: () -> Unit, modifier: Modifier = Modifier,
    enabled: Boolean = true, label: String? = null, color: Color = MaterialTheme.colorScheme.onSurface,
    style: TextStyle = ChatApparatus,
) {
    Box(modifier.sizeIn(minWidth = 48.dp, minHeight = 48.dp)
        .clickable(enabled = enabled, role = Role.Button, onClick = onClick)
        .then(if (label == null) Modifier else Modifier.semantics { contentDescription = label }),
        contentAlignment = Alignment.Center,
    ) {
        Text(text, color = if (enabled) color else MaterialTheme.colorScheme.onSurfaceVariant, style = style)
    }
}

@Composable
internal fun Heading(text: String) {
    Text(text, Modifier.semantics { heading() }, style = MaterialTheme.typography.headlineLarge)
}

@Composable
internal fun BodyStatus(text: String) {
    Text(text, Modifier.semantics { liveRegion = LiveRegionMode.Polite }, color = MaterialTheme.colorScheme.onSurfaceVariant)
}
