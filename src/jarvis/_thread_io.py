"""Join entered blocking file work before its caller releases owned resources."""

import asyncio
from collections.abc import Callable


async def finish_entered[T](entered: asyncio.Task[T]) -> T:
    while True:
        try:
            return await asyncio.shield(entered)
        except asyncio.CancelledError:
            if entered.done():
                return entered.result()


async def joined_thread[T, **P](
    operation: Callable[P, T], *args: P.args, **kwargs: P.kwargs
) -> T:
    entered = asyncio.create_task(asyncio.to_thread(operation, *args, **kwargs))
    try:
        return await asyncio.shield(entered)
    except asyncio.CancelledError as cancellation:
        try:
            await finish_entered(entered)
        finally:
            raise cancellation
