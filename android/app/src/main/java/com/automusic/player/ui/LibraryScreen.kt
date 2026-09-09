package com.automusic.player.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Delete
import androidx.compose.material.icons.outlined.MusicNote
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.automusic.player.AppContainer
import com.automusic.player.core.db.ScoreEntity
import com.automusic.player.ui.theme.Bg
import com.automusic.player.ui.theme.Brand
import com.automusic.player.ui.theme.Ink2
import com.automusic.player.ui.theme.Ink3
import com.automusic.player.ui.theme.StateError
import kotlinx.coroutines.launch

/** 乐谱库:SQLite 本地存储,保存过一次即可反复演奏。 */
@Composable
fun LibraryScreen(container: AppContainer, onGoPlay: () -> Unit) {
    val scope = rememberCoroutineScope()
    val scores by container.db.scoreDao().observeAll().collectAsState(initial = emptyList())
    var deleting by remember { mutableStateOf<ScoreEntity?>(null) }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("乐谱库", style = MaterialTheme.typography.titleLarge)
        if (scores.isEmpty()) {
            Spacer(Modifier.height(32.dp))
            Text(
                "还没有乐谱。到「识别」页上传乐谱并保存后,即可在这里反复演奏。",
                color = Ink3,
                style = MaterialTheme.typography.bodyMedium,
            )
        } else {
            LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                items(scores, key = { it.id }) { score ->
                    Card(
                        colors = CardDefaults.cardColors(containerColor = com.automusic.player.ui.theme.Surface1),
                        modifier = Modifier
                            .fillMaxWidth()
                            .clickable {
                                container.selectedScoreId = score.id
                                onGoPlay()
                            },
                    ) {
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(14.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Icon(
                                Icons.Outlined.MusicNote,
                                contentDescription = null,
                                tint = Brand,
                            )
                            Column(
                                Modifier
                                    .weight(1f)
                                    .padding(start = 12.dp),
                            ) {
                                Text(score.name, style = MaterialTheme.typography.titleMedium)
                                Text(
                                    "${score.createdAt} · 默认 ${score.bpmDefault} BPM",
                                    color = Ink2,
                                    style = MaterialTheme.typography.bodySmall,
                                )
                            }
                            IconButton(onClick = { deleting = score }) {
                                Icon(
                                    Icons.Outlined.Delete,
                                    contentDescription = "删除",
                                    tint = StateError,
                                )
                            }
                        }
                    }
                }
            }
        }
    }

    deleting?.let { score ->
        AlertDialog(
            onDismissRequest = { deleting = null },
            title = { Text("删除乐谱") },
            text = { Text("确定删除「${score.name}」?该操作不可撤销。") },
            confirmButton = {
                TextButton(onClick = {
                    scope.launch { container.db.scoreDao().delete(score.id) }
                    deleting = null
                }) { Text("删除", color = StateError) }
            },
            dismissButton = {
                TextButton(onClick = { deleting = null }) { Text("取消", color = Ink2) }
            },
        )
    }
}
