# Vigiliarium

Vigiliarium 是一个专注于长期项目推进的小工具，出于我自己的需要而开发。主要给学者和研究者使用：手上同时开着几个项目，也很容易拖延，因此往往需要一个打开成本很低的地方记一下“今天碰过哪个项目”。它不做复杂的任务管理，也不打算替代其他 GTD 工具。

名字来自拉丁语的“守望塔”。
老普林尼在《自然志》里写过一句“Vita vigilia est”，意思是“生命即警醒/守望”，名字取意于此。

数据全部存放在普通的 Markdown 文件里，没有数据库、不联网、不调用 AI、不需要账号。
可以用 pip 安装，也可以编译成单个二进制文件。

## 功能

- 每天设一个重点，首页直接显示。
- 阅读、写作、邮件、杂务四项例行事项，可以打卡，也可以取消。
- 用一到两次按键记录“今天推进了某个项目”，备注可以留空。
- 项目支持新建，以及修改状态、当前、下一步、截止日期、阶段和标题。状态有进行中、等待中、已暂停、想法、已完成五种。
- 回顾关注连续性：最近一次推进是几天前，最近 7 天和 30 天分别碰过几天；也能看单个项目的推进历史和一周的情况。
- 超过 7 天没碰过的项目会显示一个感叹号，只作提醒，不给评分。
- 所有数据都是纯文本，可以直接编辑、grep、放进 Git 或交给同步工具。

## 安装

需要 Python 3.11 或更高版本：

```
python3 -m pip install .
```

安装后直接运行 `vigi`。

也可以构建单文件二进制（约 6 MB，需要 glibc 2.36 以上）：

```
bash packaging/build.sh
```

产物是 dist/vigi。构建需要 podman 或 docker。也可以直接在 GitHub Releases 下载预编译的 vigi-x86_64-linux。

## 数据目录

程序按以下顺序确定数据目录：命令行参数 --dir、环境变量 vigi_DIR、默认的 ~/.local/share/vigi。
目录不存在时会自动创建。用 `vigi info` 可以查看最终实际使用的目录。

```
vigi --dir ~/Documents/vigi
export vigi_DIR="$HOME/Documents/vigi"
```

目录下有 projects（项目文件）、days（每日记录）和 archive 三个子目录。

## 界面

运行 vigi 进入 TUI，全部用键盘操作。首页用 `↑↓` 或 `j`/`k` 移动选择，`Enter` 查看项目，
`f` 设为今日重点，`F` 清除今日重点，`t` 推进选中项目，`d` 例行打卡，`n` 添加今日备注，`e` 用 `$EDITOR` 编辑今日记录，
`c` 新建项目，`a` 切换“进行中 / 全部项目”，`A` 查看归档项目，`r` 项目回顾（可 `Enter` 打开项目），`w` 周回顾，
`R` 重新读取数据，`?` 帮助，`q` 退出。今日备注会直接显示在首页。

列表或内容过长时可用 `↑↓`（或 `j`/`k`）滚动：首页项目、项目回顾、归档、周回顾、帮助页、项目详情的历史记录都支持。
终端支持颜色时，会用少量颜色区分标题、今日重点、已完成的例行事项和久未推进的提醒。

进入项目页后，`t` 推进，`n` 推进并写备注，`c` 修改“当前”，`x` 修改“下一步”，
`s` 修改状态，`e` 用 `$EDITOR` 编辑项目文件，`d` 删除（按 y 确认），`A` 归档，`q` 返回。

## 命令行

命令用英文，输出用中文。

```
vigi info                          显示实际使用的数据目录
vigi projects                      列出项目
vigi focus ID                      设置今日重点
vigi focus --clear                 清除今日重点
vigi touch ID [-m "备注"]          标记今天推进过
vigi current ID "…"                修改“当前”，传空字符串清除
vigi next ID "…"                   修改“下一步”
vigi done reading                  例行打卡（reading/writing/email/admin）
vigi undo reading                  取消打卡
vigi note "内容"                   添加今日备注
vigi today                         查看今日记录（重点 / 例行 / 项目 / 备注）
vigi review                        项目回顾
vigi review --all                  项目回顾（含非进行中项目）
vigi review --week                 周回顾
vigi new "标题" --id ID [--stage S] [--deadline YYYY-MM-DD]
vigi edit ID                       用 $EDITOR 编辑项目文件
vigi archive ID                    归档项目（移动到 archive/）
vigi unarchive ID                  取消归档（移回 projects/）
vigi projects --archived           列出已归档项目
vigi delete ID                     删除项目（默认需确认，-y 跳过）
```

## 文件格式

每个项目对应 projects 下的一个 Markdown 文件，文件名就是项目 ID（例如 projects/irrigation-history.md）：

```
# 示例项目：山区村落的灌溉系统

Status: active
Stage: 初稿
Deadline: 2026-11-30

## Current

整理第三章的访谈记录。

## Next

补充水利志里的相关条目。

## Log

- 2026-10-01 — 第三章第一节初步成形。
- 2026-09-30 — 整理了第一批访谈记录。
```

Status 只能取 active、waiting、paused、idea、done 之一。

每天的记录是 days 下的一个文件，文件名是日期：

```
# 2026-10-01

Focus: irrigation-history

## Routine

- [x] Reading
- [ ] Writing
- [ ] Email
- [ ] Admin

## Projects

- [x] irrigation-history

## Notes

- 灌溉系统的第三章材料整理了一部分。
```

例行事项固定为 Reading、Writing、Email、Admin 四项，文件中始终使用英文名。

## 备份

数据目录就是一个普通文件夹，复制或同步即可：

```
cp -a ~/.local/share/vigi ~/backup/vigi-$(date +%F)
rsync -a ~/.local/share/vigi/ ~/backup/vigi/
```

程序本身不实现云同步，可以自行使用 Git、Syncthing、坚果云等工具。

## 开发

```
python3 -m unittest discover -v
```

项目只使用 Python 标准库。

## 许可

GPL-3.0-or-later，见 LICENSE。
