from abc import ABC, abstractmethod

class IState(ABC):
    @abstractmethod
    def update(self) -> None:
        pass
    @abstractmethod
    def enter(self,args: list | None = None) -> None:
        pass
    @abstractmethod
    def exit(self) -> None:
        pass

class EmptyState(IState):
    def enter(self, args: list | None = None) -> None:
        return
    def update(self) -> None:
        return
    def exit(self) -> None:
        return


