from lobster_agent.persistence.db import create_db_engine, create_db_schema, create_sessionmaker
from lobster_agent.persistence.repositories import ConversationRepository
from lobster_agent.telegram.memory import ConversationMemory


async def _setup(tmp_path, max_turns: int = 20):
    engine = create_db_engine(f"sqlite+aiosqlite:///{tmp_path / 'state.db'}")
    await create_db_schema(engine)
    session_maker = create_sessionmaker(engine)
    repo = ConversationRepository(session_maker)

    async def repo_factory() -> ConversationRepository:
        return repo

    memory = ConversationMemory(repo_factory, max_turns=max_turns)
    return repo, memory, engine


async def test_append_stores_in_cache_and_calls_repo(tmp_path) -> None:
    repo, memory, engine = await _setup(tmp_path)
    await memory.append(42, "user", "hola", "chat")
    assert memory.get_history(42) == [("user", "hola")]
    turns = await repo.load_recent(42, 10)
    assert len(turns) == 1
    assert turns[0].role == "user"
    assert turns[0].content == "hola"
    await engine.dispose()


async def test_warm_up_loads_from_sqlite(tmp_path) -> None:
    repo, memory, engine = await _setup(tmp_path)
    # Persist a turn directly via repo (bypassing memory cache)
    await repo.append(7, "user", "desde BD", "chat")
    # Cache should be empty
    assert memory.get_history(7) == []
    # warm_up should populate it
    await memory.warm_up(7)
    assert memory.get_history(7) == [("user", "desde BD")]
    await engine.dispose()


async def test_warm_up_skips_if_already_cached(tmp_path) -> None:
    repo, memory, engine = await _setup(tmp_path)
    # Pre-populate cache via append
    await memory.append(5, "user", "en cache", "chat")
    # Insert a different row directly in DB (should NOT appear after warm_up since 5 is cached)
    await repo.append(5, "assistant", "solo en BD", "chat")
    # warm_up must be a no-op
    await memory.warm_up(5)
    history = memory.get_history(5)
    assert history == [("user", "en cache")]
    assert ("assistant", "solo en BD") not in history
    await engine.dispose()


async def test_get_history_returns_correct_order(tmp_path) -> None:
    repo, memory, engine = await _setup(tmp_path)
    await memory.append(1, "user", "primero", "chat")
    await memory.append(1, "assistant", "segundo", "chat")
    await memory.append(1, "user", "tercero", "chat")
    history = memory.get_history(1)
    assert history == [("user", "primero"), ("assistant", "segundo"), ("user", "tercero")]
    await engine.dispose()


async def test_trim_drops_oldest_from_ram_sqlite_keeps_all(tmp_path) -> None:
    repo, memory, engine = await _setup(tmp_path, max_turns=3)
    for i in range(4):
        await memory.append(9, "user", f"msg{i}", "chat")
    history = memory.get_history(9)
    # RAM: only last 3
    assert len(history) == 3
    assert history[0] == ("user", "msg1")
    assert history[-1] == ("user", "msg3")
    # SQLite: all 4
    all_turns = await repo.load_recent(9, 10)
    assert len(all_turns) == 4
    await engine.dispose()


async def test_clear_empties_cache_and_calls_repo(tmp_path) -> None:
    repo, memory, engine = await _setup(tmp_path)
    await memory.append(3, "user", "borrar esto", "chat")
    assert memory.get_history(3) != []
    await memory.clear(3)
    assert memory.get_history(3) == []
    turns = await repo.load_recent(3, 10)
    assert turns == []
    await engine.dispose()
