from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QTextEdit, QVBoxLayout


class ConfigurationLoadError(Exception):
    """Raised when the Configuration.tex could not be found or opened."""

    pass


def display_info_window(
    config_tex, search_list, width, valid_only, show_urls, calling_window, font=None, fg="white", bg="black"
):
    """Display a Configuration.tex info window using Qt widgets."""
    try:
        result = parse_configuration_tex(config_tex, search_list, width, valid_only, show_urls)
    except ConfigurationLoadError:
        QApplication.beep()
        QMessageBox.critical(
            calling_window,
            "Configuration.tex Error",
            "Could not find/open Configuration.tex at: {}".format(config_tex or "No Path Specified"),
        )
        return

    title = " -> ".join([x for x in search_list if not x == "*"])

    if not result:
        QApplication.beep()
        QMessageBox.critical(calling_window, "Info Not Found", 'No info found for: "{}"'.format(title))
        return

    # Build the dialog
    dlg = QDialog(calling_window)
    dlg.setWindowTitle('"{}" Info'.format(title))
    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(0, 0, 0, 0)

    text_edit = QTextEdit()
    text_edit.setReadOnly(True)
    text_edit.setStyleSheet("QTextEdit {{ background-color: {}; color: {}; }}".format(bg, fg))
    text_edit.setLineWrapMode(QTextEdit.WidgetWidth)
    layout.addWidget(text_edit)

    # Set up fonts
    base_font = font or QFont()
    mono_font = QFont("Courier New", base_font.pointSize())

    # Build text char formats for each style
    def _make_fmt(f=None, bold=False, italic=False, underline=False, color=None, bg_color=None, fg_override=None):
        fmt = QTextCharFormat()
        fmt.setFont(f or base_font)
        if bold:
            fmt.setFontWeight(QFont.Bold)
        if italic:
            fmt.setFontItalic(True)
        if underline:
            fmt.setFontUnderline(True)
        if color:
            fmt.setForeground(QColor(color))
        if bg_color:
            fmt.setBackground(QColor(bg_color))
        if fg_override:
            fmt.setForeground(QColor(fg_override))
        return fmt

    formats = {
        "normal": _make_fmt(),
        "bold": _make_fmt(bold=True),
        "bold_mono": _make_fmt(f=mono_font, bold=True),
        "italic": _make_fmt(italic=True),
        "underline": _make_fmt(underline=True),
        "mono": _make_fmt(f=mono_font),
        "url": _make_fmt(f=mono_font, color="dodgerblue"),
        "reverse": _make_fmt(bg_color="white", fg_override="black"),
    }

    # Parse escape sequences and insert formatted text
    cursor = text_edit.textCursor()
    style = "normal"
    in_escape = False
    esc_code = ""
    out = ""

    def flush(out, style):
        if out:
            cursor.insertText(out, formats.get(style, formats["normal"]))

    for c in result:
        if in_escape:
            esc_code += c
            if c == "m":
                if esc_code == "[0m":
                    style = "normal"
                if esc_code == "[10m":
                    style = "normal"
                if esc_code == "[1m":
                    style = "bold_mono" if style == "mono" else "bold"
                if esc_code == "[22m":
                    style = "mono" if style == "bold_mono" else "normal"
                if esc_code == "[3m":
                    style = "italic"
                if esc_code == "[4m":
                    style = "underline"
                if esc_code == "[11m":
                    style = "mono"
                if esc_code == "[7m":
                    style = "reverse"
                if esc_code == "[34m":
                    style = "url" if show_urls else "mono"
                out = ""
                esc_code = ""
                in_escape = False
            continue
        if c == "\x1b":
            flush(out, style)
            out = ""
            in_escape = True
            continue
        out += c

    if out:
        flush(out, style)

    text_edit.moveCursor(QTextCursor.Start)

    # Size and position the dialog
    dlg.resize(800, 600)
    if calling_window:
        cg = calling_window.geometry()
        dlg.move(cg.x() + (cg.width() - 800) // 2, cg.y() + 30)
    dlg.show()
    return dlg


def parse_configuration_tex(config_file, search_list, width, valid_only, show_urls):
    # valid_only: True - return only the valid config.plist options for the search term &
    # return an empty list if no valid options found
    #     False: return whole text of section
    #
    # show_urls: True - return full url of links in the text
    #     False - return only link text with no url
    try:
        config = open(config_file, "r")
    except Exception:
        raise ConfigurationLoadError

    result = []
    search_len = len(search_list)
    if search_len == 0:  # we shouldn't get here, but just in case
        return result

    search_terms = ["\\section{"]
    search_terms[0] += search_list[0]
    text_search = search_list[search_len - 1]  # ultimately looking for last item

    # set the search terms based on selected position
    if search_len == 1:
        # we're done
        pass
    elif search_len == 2:
        search_terms.append("\\subsection{Properties")
        search_terms.append("texttt{" + text_search + "}\\")
    elif search_len == 3:
        if search_list[0] == "NVRAM":  # look for value in Introduction
            search_terms.append("\\subsection{Introduction")
            search_terms.append("texttt{" + text_search + "}")
        else:
            search_terms.append("\\subsection{" + search_list[1] + " Properties")
            search_terms.append("texttt{" + text_search + "}\\")
    elif search_len == 4:
        item_zero = search_list[0]
        sub_search = "\\subsection{"
        if item_zero == "NVRAM":  # look for UUID:term in Introduction
            sub_search = "\\subsection{Introduction"
            text_search = search_list[2]
            text_search += ":"
            text_search += search_list[3]
            text_search += "}"
        elif item_zero == "DeviceProperties":  # look in Common
            sub_search += "Common"
            text_search += "}"
        elif item_zero == "Misc":  # Entry Properties or subsub
            if len(search_list[2]) < 3:
                sub_search += "Entry Properties"
            else:
                sub_search = "\\subsubsection{"
                sub_search += search_list[1]
            text_search += "}"
        else:
            sub_search += search_list[1]
            sub_search += " Properties"
            text_search += "}\\"
        search_terms.append(sub_search)
        search_terms.append("texttt{" + text_search)
    elif search_len == 5:
        sub_search = "\\subsubsection{"
        sub_search += search_list[1]
        search_terms.append(sub_search)
        search_terms.append("texttt{" + text_search)

    # keep a set of prefixes that would break us out of our search
    disallowed = set()
    # move down the Configuration.tex to the section we want
    for i in range(0, len(search_terms)):
        while True:
            line = config.readline()
            if not line:
                return result
            line = line.strip()
            # Check for disallowed
            if line.startswith(tuple(disallowed)) and (
                search_terms[0] != "\\section{NVRAM" or "\\label{nvram" not in line
            ):
                # We've broken out of our current scope - bail
                return result
            if search_terms[i] in line:
                # Make sure parent search prefixes get added
                # to the disallowed set
                if not search_terms[i].startswith("texttt{"):
                    # Retain the prefix as needed
                    disallowed.add(search_terms[i].split("{")[0] + "{")
                break

    align = False
    itemize = 0
    not_first_item = False
    in_listing = False
    enum = 0
    columns = 0
    lines_between_valid = 0
    last_line_ended_in_colon = False
    last_line_had_forced_return = False
    last_line_ended_in_return = False
    last_line_was_blank = False

    while True:
        # track document state & preprocess line before parsing
        line = config.readline()
        if not line:
            break
        line = line.strip()
        if line.startswith("%"):  # skip comments
            continue
        if "\\subsection{Introduction}" in line:
            continue
        if "\\begin{tabular}" in line:
            result.append("\x1b[11m")
            for c in line:
                if c == "c":
                    columns += 1
            continue
        if "\\begin(align*}" in line:
            align = True
            continue
        if "\\end{align*}}" in line:
            align = False
            continue
        if "\\begin{itemize}" in line:
            itemize += 1
            continue
        if "\\begin{enumerate}" in line:
            enum += 1
            continue
        if "\\begin{lstlisting}" in line:
            in_listing = True
            result.append("\n\x1b[11m")
            result.append("-" * width)
            result.append("\n")
            continue
        if "\\begin{" in line:  # ignore other begins
            continue
        if "\\mbox" in line:
            continue
        if "\\end{tabular}" in line:
            result.append("\x1b[10m")
            columns = 0
            continue
        if "\\end{itemize}" in line:
            itemize -= 1
            if itemize == 0 and enum == 0:
                not_first_item = False
            continue
        if "\\end{enumerate}" in line:
            enum = 0
            if itemize == 0:
                not_first_item = False
            continue
        if "\\end{lstlisting}" in line:
            in_listing = False
            result.append("-" * width)
            result.append("\x1b[10m\n")
            continue
        if "\\end{" in line:  # ignore other ends
            continue
        if "\\item" in line:
            if itemize == 0 and enum == 0:
                break  # skip line, not itemizing, shouldn't get here
            else:
                if not_first_item or not last_line_ended_in_return:
                    # newline before this item
                    result.append("\n")
                not_first_item = True
                if itemize == 0:  # in enum
                    if search_len == 1:  # first level enumerate, use numeric
                        replace_str = str(enum) + "."
                    else:  # use alpha
                        replace_str = "(" + chr(96 + enum) + ")"
                    line = line.replace("\\item", replace_str)
                    enum += 1
                elif itemize == 1:  # first level item
                    line = line.replace("\\item", "\u2022")
                else:
                    line = line.replace("\\item", "-")
                # fix indenting
                line = "    " * itemize + line
                if enum != 0:
                    line = "    " + line
        else:
            if itemize > 0 or enum > 0:  # inside multi line item
                if last_line_had_forced_return:
                    line = "    " * itemize + line
                    line = "       " + line  # indent
        if "section{" in line:  # stop when next section is found
            # let's try only checking for "section{" instead of 3 checks
            #        if "\\section{" in line or "\\subsection{" in line or "\\subsubsection{" in line:
            # reached end of current section
            break

        if line.strip() == "":  # blank line, need linefeed, maybe two, maybe none
            if last_line_ended_in_colon:
                parsed_line = "\n"
            else:
                if last_line_was_blank:  # skip this blank line
                    continue
                else:
                    parsed_line = "\n\n"
            last_line_was_blank = True
        else:
            last_line_was_blank = False
            parsed_line = parse_line(line, columns, width, align, valid_only, show_urls)
            if len(parsed_line) == 0:
                continue
            # post process line
            last_line_had_forced_return = False
            last_line_ended_in_colon = False
            if parsed_line.endswith("\n"):
                last_line_had_forced_return = True
            elif parsed_line.endswith(":"):
                parsed_line += "\n"
                if not_first_item:
                    # treat as forced return instead
                    last_line_had_forced_return = True
                else:
                    last_line_ended_in_colon = True
            else:
                parsed_line += " "  # add space for next word

        if parsed_line.endswith("\n"):
            # slightly different use than last_line_had_forced_return
            last_line_ended_in_return = True
        else:
            last_line_ended_in_return = False
        if valid_only:  # we only want to return valid plist options for the field
            if itemize > 0:
                if "---" in line:
                    if lines_between_valid < 10:
                        result.append(parsed_line)
            else:
                if len(result) > 0:
                    lines_between_valid += 1
        else:
            result.append(parsed_line)
            if in_listing:
                result.append("\n")
    # Join the result into a single string and remove
    # leading, trailing, and excessive newlines
    # result = re.sub(r"\n{2,}",r"\n\n","".join(result))
    # return result.strip("\n")

    # leave all excess internal newlines for now for easier debugging
    return "".join(result).strip("\n")

    # return re.sub("\n{2,}", "\n\n", "".join(result)).strip("\n")


def parse_line(line, columns, width, align, valid_only, show_urls):
    ret = ""
    build_key = False
    key = ""
    col_width = 0
    if columns > 0:
        col_width = int(width / (columns + 1))
    ignore = False
    col_contents_len = 0
    line = line.rstrip()
    for c in line:
        if build_key:
            if c in "{[":
                build_key = False
                if not valid_only:
                    if key == "text":
                        ret += "\x1b[0m"
                    elif key == "textit":
                        ret += "\x1b[3m"
                    elif key == "textbf":
                        ret += "\x1b[1m"
                    elif key == "emph":
                        ret += "\x1b[3m"
                    elif key == "texttt":
                        ret += "\x1b[11m"
                    elif key == "href":
                        if show_urls:
                            ret += "\x1b[34m"
                        else:
                            ignore = True
                    else:
                        ignore = True
                if key != "href":
                    key = ""
            elif c in " ,()\\0123456789$&":
                build_key = False
                ret += special_char(key)
                col_contents_len += 1
                if c in ",()0123456789$":
                    ret += c
                if c == "\\":
                    if len(key) > 0:
                        build_key = True
                key = ""
            elif c in "_^#":
                build_key = False
                ret += c
                col_contents_len += 1
                key = ""
            else:
                key += c
        else:
            if c == "\\":
                build_key = True
            elif c in "}]":
                if not ignore:
                    if not valid_only:
                        if columns > 0:
                            ret += "\x1b[22m"
                        else:
                            ret += "\x1b[0m"
                        if key == "href":
                            # ret += " "
                            key = ""
                        elif c == "]":
                            ret += "]"
                ignore = False
            elif c == "{":
                if not valid_only:
                    ret += "\x1b[11m"
            elif c == "&":
                if columns > 0:
                    pad = col_width - col_contents_len - 1
                    if pad > 0:
                        ret += " " * pad
                    col_contents_len = 0
                    ret += "|"
                else:
                    if not align:
                        ret += "&"
            else:
                if not ignore:
                    ret += c
                    col_contents_len += 1

    if len(key) > 0:
        ret += special_char(key)

    if not valid_only:
        if key == "tightlist":
            ret = ""
        else:
            if key == "hline":
                ret = "-" * (width - 4)
                ret += "\n"
        if line.endswith("\\\\"):
            ret += "\n"
    return ret


def special_char(key):
    if key == "kappa":
        return "\u03f0"
    elif key == "lambda":
        return "\u03bb"
    elif key == "mu":
        return "\u03bc"
    elif key == "alpha":
        return "\u03b1"
    elif key == "beta":
        return "\u03b2"
    elif key == "gamma":
        return "\u03b3"
    elif key == "leq":
        return "\u2264"
    elif key == "cdot":
        return "\u00b7"
    elif key == "in":
        return "\u220a"
    elif key == "infty":
        return "\u221e"
    elif key == "textbackslash":
        return "\\"
    elif key == "hline":
        return "\u200b"
    else:
        return " "
