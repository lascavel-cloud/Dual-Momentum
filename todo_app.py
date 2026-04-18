import json

class ToDo:
    def __init__(self, task, completed=False):
        self.task = task
        self.completed = completed

    def mark_complete(self):
        self.completed = True

class ToDoList:
    def __init__(self, filename='todos.json'):
        self.todos = []
        self.filename = filename
        self.load_from_storage()

    def add_task(self, task):
        new_task = ToDo(task)
        self.todos.append(new_task)
        self.save_to_storage()

    def remove_task(self, task):
        self.todos = [todo for todo in self.todos if todo.task != task]
        self.save_to_storage()

    def mark_task_complete(self, task):
        for todo in self.todos:
            if todo.task == task:
                todo.mark_complete()
                self.save_to_storage()
                break

    def save_to_storage(self):
        with open(self.filename, 'w') as file:
            json.dump([{'task': todo.task, 'completed': todo.completed} for todo in self.todos], file)

    def load_from_storage(self):
        try:
            with open(self.filename, 'r') as file:
                todos_data = json.load(file)
                self.todos = [ToDo(todo['task'], todo['completed']) for todo in todos_data]
        except (FileNotFoundError, json.JSONDecodeError):
            self.todos = []

    def show_tasks(self):
        for todo in self.todos:
            status = '✓' if todo.completed else '✗'
            print(f'{status} {todo.task}') 

if __name__ == '__main__':
    todo_list = ToDoList()
    while True:
        action = input("Enter 'add', 'remove', 'complete', or 'show' to manage your tasks (type 'exit' to quit): ").strip().lower()
        if action == 'add':
            task = input('Enter a task: ')
            todo_list.add_task(task)
        elif action == 'remove':
            task = input('Enter a task to remove: ')
            todo_list.remove_task(task)
        elif action == 'complete':
            task = input('Enter a task to mark complete: ')
            todo_list.mark_task_complete(task)
        elif action == 'show':
            todo_list.show_tasks()
        elif action == 'exit':
            break
        else:
            print("Invalid action. Please try again.")