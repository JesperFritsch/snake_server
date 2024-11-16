import asyncio

class TaskManager:
    def __init__(self):
        self.tasks = set()

    def add_task(self, task):
        self.tasks.add(task)
        task.add_done_callback(self.tasks.remove)

    async def cancel_all(self):
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks.clear()