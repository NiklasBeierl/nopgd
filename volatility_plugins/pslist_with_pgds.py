# This file is Copyright 2019 Volatility Foundation and licensed under the Volatility Software License 1.0
# which is available at https://www.volatilityfoundation.org/license/vsl-v1.0
#

from itertools import chain
from typing import Callable, Iterable, List, Any
from volatility3.framework import renderers, interfaces, contexts
from volatility3.framework.configuration import requirements
from volatility3.framework.objects import utility
from volatility3.framework.exceptions import PagedInvalidAddressException


class PsListWithPGDs(interfaces.plugins.PluginInterface):
    """Lists the processes present in a particular linux memory image with the the virtual addresses of their
    mm and active_mm as well as the corresponding values of the mm_struct->pgd"""

    _required_framework_version = (1, 0, 0)

    _version = (1, 0, 0)

    @classmethod
    def get_requirements(cls) -> List[interfaces.configuration.RequirementInterface]:
        return [
            requirements.TranslationLayerRequirement(
                name="primary",
                description="Memory layer for the kernel",
                architectures=["Intel32", "Intel64"],
            ),
            requirements.SymbolTableRequirement(name="vmlinux", description="Linux kernel symbols"),
            requirements.ListRequirement(
                name="pid",
                description="Filter on specific process IDs",
                element_type=int,
                optional=True,
            ),
        ]

    @classmethod
    def create_pid_filter(cls, pid_list: List[int] = None) -> Callable[[Any], bool]:
        """Constructs a filter function for process IDs.

        Args:
            pid_list: List of process IDs that are acceptable (or None if all are acceptable)

        Returns:
            Function which, when provided a process object, returns True if the process is to be filtered out of the list
        """
        pid_list = pid_list or []
        filter_list = [x for x in pid_list if x is not None]
        if filter_list:

            def filter_func(x):
                return x.pid not in filter_list

            return filter_func
        else:
            return lambda _: False

    def _generator(self):
        for task, mm, active_mm in self.list_tasks(
            self.context,
            self.config["primary"],
            self.config["vmlinux"],
            filter_func=self.create_pid_filter(self.config.get("pid", None)),
        ):
            if task.mm:
                # https://elixir.bootlin.com/linux/latest/source/arch/x86/include/asm/pgtable.h#L1168
                # All top-level PAGE_TABLE_ISOLATION page tables are order-1 pages (8k-aligned and 8k in size).
                # The kernel one is at the beginning 4k and the user one is in the last 4k.
                # To switch between them, you just need to flip the 12th bit in their addresses.
                ppid = task.parent.pid if task.parent else 0
                pgd = task.mm.pgd
                phy_pgd = self.context.layers["primary"].translate(pgd)[0]
                try:
                    kernel_pgd_vaddr = pgd & ~(1 << 12)
                    phy_kernel_pgd = self.context.layers["primary"].translate(kernel_pgd_vaddr)[0]
                except PagedInvalidAddressException:
                    phy_kernel_pgd = -1

                try:
                    user_pgd_vaddr = pgd | (1 << 12)
                    phy_user_pgd = self.context.layers["primary"].translate(user_pgd_vaddr)[0]
                except PagedInvalidAddressException:
                    phy_user_pgd = -1
                name = utility.array_to_string(task.comm)
                yield 0, (task.pid, ppid, name, phy_pgd, phy_kernel_pgd, phy_user_pgd)

    @classmethod
    def list_tasks(
        cls,
        context: interfaces.context.ContextInterface,
        layer_name: str,
        vmlinux_symbols: str,
        filter_func: Callable[[int], bool] = lambda _: False,
    ) -> Iterable[interfaces.objects.ObjectInterface]:
        """Lists all the tasks in the primary layer.

        Args:
            context: The context to retrieve required elements (layers, symbol tables) from
            layer_name: The name of the layer on which to operate
            vmlinux_symbols: The name of the table containing the kernel symbols
        Yields:
            3-tuples of task, mm, active_mm, the later two may be None.
        """
        vmlinux = contexts.Module(context, vmlinux_symbols, layer_name, 0)
        init_task = vmlinux.object_from_symbol(symbol_name="init_task")

        for task in chain([init_task], init_task.tasks):
            if not filter_func(task):
                mm = vmlinux.object("mm_struct", task.mm) if task.mm else None
                active_mm = vmlinux.object("mm_struct", task.active_mm) if task.active_mm else None
                yield task, mm, active_mm

    def run(self):
        return renderers.TreeGrid(
            [
                ("PID", int),
                ("PPID", int),
                ("COMM", str),
                ("phy_pgd", int),
                ("phy_pgd_kernel", int),
                ("phy_pgd_user", int),
            ],
            self._generator(),
        )
