## 字节复核最终结果

c2f6ff8 添加保字节属性后，普通 git add 没有更新已缓存的提案内容，第二次复核仍失败；原文保存为 git-archive-byte-final-output.txt，该文件名中的final不代表通过。

随后实际执行：

```powershell
git check-attr text whitespace -- artifacts/step3/checkpoint-4/nsis-install-directory-proposal.diff
git add --renormalize -- artifacts/step3/checkpoint-4/nsis-install-directory-proposal.diff
```

属性输出text/whitespace均unset；强制重索引后a02f5f9归档原始238字节。最终成功收据是 **git-archive-byte-reindexed-output.txt**：git_blob_files_checked=304、all_archived_bytes_match_manifest=true。工作区304文件17,381,611字节也与原清单全部一致，清单SHA256仍为847098f88fe07055744a11c29d54324fa4ceb74d4ac029d0106ec70f2f03d719。没有改写原manifest来迁就Git归一化结果。

REPORT.md及原始测量内容保持不变；后续复核以本补记与成功收据补充其归档状态。所有安装、VM和未捕获UI项目的状态不变。
