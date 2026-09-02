from states import IState,EmptyState

class StateMachine:
    _stateDict: dict[str,IState]
    _current: IState

    def __init__(self,states: dict[str,IState] | None = None,args: list | None = None) -> None:
        if states:
            self._stateDict = states

            self._current = next(iter(states.values()))
            self._current.enter(args)
            return

        self._stateDict = dict()
        self._current = EmptyState()

    def add(self,id: str,state: IState) -> None:
        self._stateDict[id] = state
    def remove(self,id: str) -> None:
        self._stateDict.pop(id,None)
    def clear(self) -> None:
        self._stateDict.clear()

    def change(self,id: str,args: list | None = None):
        self._current.exit()
        next = self._stateDict[id]
        next.enter(args)
        self._current = next

    def update(self):
        self._current.update()

