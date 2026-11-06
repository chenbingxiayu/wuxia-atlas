# registry/patches/

补标建议 TSV **按书子目录**存放（2026-11-05 起，docs/47 §八）：

    registry/patches/<book>/<NNN>_<kind>.tsv

- kind：aliases(C18) / identity_kinship(C17) / new_entities(C16) / boundary_fix(C20) /
  recall_pass(C25) / <book>_entity_registration.json
- 产生方：scan_untagged_aliases / tag_identity_kinship / tag_new_entity_types /
  detect_entity_boundary_errors / apply_gold_calibrated_recall（均经 config.patches_dir(book)）
- 应用方：apply_annotation_patches.py --dir（不带值 + --book <书名>）

历史：2026-11-05 前为扁平 `<NNN>_<kind>.tsv`，因多书章号冲突（江湖三女侠 034-048 与
白发魔女传 001-032）已全部迁入子目录。扁平遗留 `_backup_entities_*.json` 为
apply_entity_registration 旧版备份（书归属未定，暂留）。
