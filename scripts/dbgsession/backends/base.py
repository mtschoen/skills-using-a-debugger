"""Abstract base class defining the uniform verb interface for all debugger backends."""

from abc import ABC, abstractmethod


class Backend(ABC):
    @abstractmethod
    def start(self) -> None: ...

    @abstractmethod
    def set_breakpoint(self, file: str, line: int) -> str: ...

    @abstractmethod
    def run(self) -> str: ...

    @abstractmethod
    def cont(self) -> str: ...

    @abstractmethod
    def step_over(self) -> str: ...

    @abstractmethod
    def step_into(self) -> str: ...

    @abstractmethod
    def read_local(self, name: str) -> str: ...

    @abstractmethod
    def backtrace(self) -> str: ...

    @abstractmethod
    def raw(self, command: str) -> str: ...

    @abstractmethod
    def stop(self) -> None: ...
