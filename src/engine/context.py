#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BubbleTrans - 滑动窗口上下文构建器

从 SQLite 查询前 N 页 plot 字段，拼接为"前情提要"文本，
用于跨页翻译时保持角色名和剧情连贯性。
"""


class ContextEngine:
    """滑动窗口上下文构建器

    从 SQLite 中查询前 N 页的 plot 字段，拼接为"前情提要"文本。
    """

    def __init__(self, database):
        """
        参数:
            database: utils.database.Database 实例
        """
        self._db = database

    def build_context(self, folder_path: str, current_page: int,
                      window_size: int = 5, max_chars: int = 800) -> str | None:
        """为当前页构建上下文文本。

        参数:
            folder_path: 图片文件夹路径
            current_page: 当前页码（0-based）
            window_size: 滑动窗口大小（取前多少页）
            max_chars: 上下文最大字符数

        返回:
            上下文文本，无可用上下文时返回 None
        """
        if current_page <= 0:
            return None

        start = max(0, current_page - window_size)
        end = current_page - 1

        rows = self._db.get_page_range(folder_path, start, end)
        if not rows:
            return None

        lines = ["【前情提要】"]
        total_chars = 0
        for row in rows:
            plot = (row.get("plot") or "").strip()
            if not plot:
                continue
            page_label = row.get("page_index", "?")
            line = f"第{page_label}页：{plot}"
            if total_chars + len(line) > max_chars:
                lines.append("（更早的剧情已省略）")
                break
            lines.append(line)
            total_chars += len(line)

        if len(lines) == 1:  # 只有标题，无实质内容
            return None

        return "\n".join(lines)
