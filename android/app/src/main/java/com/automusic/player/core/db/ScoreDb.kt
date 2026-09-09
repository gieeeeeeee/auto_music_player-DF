package com.automusic.player.core.db

import androidx.room.Dao
import androidx.room.Database
import androidx.room.Entity
import androidx.room.Insert
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.RoomDatabase
import androidx.room.Update
import kotlinx.coroutines.flow.Flow

/** 乐谱记录:与桌面版 scores 表结构一致。 */
@Entity(tableName = "scores")
data class ScoreEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val name: String,
    val sourceFile: String,
    val sourceType: String,
    val rawText: String,
    val notesJson: String,
    val bpmDefault: Int,
    val createdAt: String,
)

@Dao
interface ScoreDao {
    @Insert
    suspend fun insert(score: ScoreEntity): Long

    @Update
    suspend fun update(score: ScoreEntity)

    @Query("SELECT * FROM scores ORDER BY createdAt DESC")
    fun observeAll(): Flow<List<ScoreEntity>>

    @Query("SELECT * FROM scores WHERE id = :id")
    suspend fun getById(id: Long): ScoreEntity?

    @Query("DELETE FROM scores WHERE id = :id")
    suspend fun delete(id: Long)
}

@Database(entities = [ScoreEntity::class], version = 1, exportSchema = false)
abstract class ScoreDb : RoomDatabase() {
    abstract fun scoreDao(): ScoreDao
}
