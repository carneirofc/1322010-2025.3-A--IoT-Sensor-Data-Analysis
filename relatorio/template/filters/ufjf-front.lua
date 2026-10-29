--[[
ufjf-front.lua — builds the ABNT pretextual pages from report.yaml.

  PDF (LaTeX): capa, folha de rosto, resumo, abstract -> `include-before`,
               so they land *before* the table of contents.
  DOCX:        the same pages as custom-styled paragraphs prepended to the
               body (styles live in template/docx/reference.docx); the TOC is
               moved after them by scripts/fix_docx.py.

It also fills document properties (title-meta, author-meta, keywords).
Only the `report:` map is read; nothing here is report-specific.
]]

local utils = pandoc.utils
local stringify = utils.stringify

local function is_empty(v)
  return v == nil or stringify(v):match('^%s*$') ~= nil
end

local function as_list(v)
  if v == nil then return {} end
  if utils.type(v) == 'List' then return v end
  return { v }
end

local function to_blocks(v)
  local t = utils.type(v)
  if t == 'Blocks' then return v end
  if t == 'Inlines' then return pandoc.Blocks { pandoc.Plain(v) } end
  return pandoc.Blocks { pandoc.Plain { pandoc.Str(stringify(v)) } }
end

local function to_inlines(v)
  if utils.type(v) == 'Inlines' then return v end
  return utils.blocks_to_inlines(to_blocks(v))
end

-- Render a metadata value to LaTeX, honouring Markdown markup and escaping.
local function tex(v)
  local out = pandoc.write(pandoc.Pandoc(to_blocks(v)), 'latex')
  return (out:gsub('%s+$', ''))
end

local function joined(list, sep)
  local parts = {}
  for _, it in ipairs(as_list(list)) do parts[#parts + 1] = stringify(it) end
  return table.concat(parts, sep)
end

-- "a. b. c."  (ABNT keyword separator)
local function keywords_text(list)
  local s = joined(list, '. ')
  if s ~= '' and not s:match('%.$') then s = s .. '.' end
  return s
end

---------------------------------------------------------------------------
-- LaTeX
---------------------------------------------------------------------------
local function latex_front(r)
  local L = {}
  local function add(s) L[#L + 1] = s end

  -- Capa
  add('\\pagestyle{empty}')
  add('\\thispagestyle{empty}')
  add('\\begingroup\\centering\\setstretch{1.15}')
  if not is_empty(r.logo) then
    add(string.format('\\includegraphics[width=%s]{%s}\\par\\vspace{0.5cm}',
      is_empty(r['logo-width']) and '5cm' or stringify(r['logo-width']),
      stringify(r.logo)))
  end
  if not is_empty(r.institution) then add('{\\large\\bfseries ' .. tex(r.institution) .. '\\par}') end
  if not is_empty(r.department) then add('{\\large ' .. tex(r.department) .. '\\par}') end
  if not is_empty(r.course) then add('\\vspace{0.4cm}{' .. tex(r.course) .. '\\par}') end
  add('\\vfill')
  for _, a in ipairs(as_list(r.authors)) do add('{\\large ' .. tex(a) .. '\\par}') end
  add('\\vfill')
  add('{\\Large\\bfseries ' .. tex(r.title) .. '\\par}')
  if not is_empty(r.subtitle) then add('\\vspace{0.3cm}{\\large ' .. tex(r.subtitle) .. '\\par}') end
  add('\\vfill')
  add('{' .. tex(r.city) .. '\\par}{' .. tex(r.year) .. '\\par}')
  add('\\endgroup')
  add('\\clearpage')

  -- Folha de rosto
  add('\\thispagestyle{empty}')
  add('\\begingroup\\centering\\setstretch{1.15}')
  for _, a in ipairs(as_list(r.authors)) do add('{\\large ' .. tex(a) .. '\\par}') end
  add('\\vspace{4cm}')
  add('{\\Large\\bfseries ' .. tex(r.title) .. '\\par}')
  if not is_empty(r.subtitle) then add('\\vspace{0.3cm}{\\large ' .. tex(r.subtitle) .. '\\par}') end
  add('\\endgroup')
  add('\\vspace{1.5cm}')
  if not is_empty(r.nature) or not is_empty(r.advisor) then
    add('\\noindent\\hfill\\begin{minipage}{0.52\\textwidth}\\setstretch{1}\\normalsize')
    if not is_empty(r.nature) then add(tex(r.nature)) end
    if not is_empty(r.advisor) then
      local label = is_empty(r['advisor-label']) and 'Orientador:' or stringify(r['advisor-label'])
      add('\\par\\vspace{0.8cm}\\noindent ' .. label .. ' ' .. tex(r.advisor))
    end
    add('\\end{minipage}\\par')
  end
  add('\\vfill')
  add('\\begingroup\\centering{' .. tex(r.city) .. '\\par}{' .. tex(r.year) .. '\\par}\\endgroup')
  add('\\clearpage')

  -- Resumo / Abstract
  local function abstract_page(heading, body, kwlabel, kws)
    if is_empty(body) then return end
    add('\\thispagestyle{empty}')
    add('\\begin{center}{\\bfseries ' .. heading .. '}\\end{center}')
    add('\\vspace{0.3cm}')
    add('\\noindent ' .. tex(body))
    if not is_empty(kws) then
      add('\\par\\vspace{0.4cm}')
      add('\\noindent\\textbf{' .. kwlabel .. '} ' .. tex(keywords_text(kws)))
    end
    add('\\clearpage')
  end
  abstract_page('RESUMO', r.resumo, 'Palavras-chave:', r['palavras-chave'])
  abstract_page('ABSTRACT', r.abstract, 'Keywords:', r.keywords)

  -- babel resets these at \begin{document}; force ABNT captions here.
  add('\\renewcommand{\\contentsname}{SUMÁRIO}')
  add('\\renewcommand{\\listfigurename}{LISTA DE FIGURAS}')
  add('\\renewcommand{\\listtablename}{LISTA DE TABELAS}')
  add('\\renewcommand{\\figurename}{Figura}')
  add('\\renewcommand{\\tablename}{Tabela}')

  return pandoc.RawBlock('latex', table.concat(L, '\n'))
end

---------------------------------------------------------------------------
-- DOCX
---------------------------------------------------------------------------
local PAGEBREAK = pandoc.RawBlock('openxml', '<w:p><w:r><w:br w:type="page"/></w:r></w:p>')

local function styled(style, inlines)
  return pandoc.Div({ pandoc.Para(inlines) }, { ['custom-style'] = style })
end

local function docx_front(r)
  local B = pandoc.Blocks {}
  local function add(b) B:insert(b) end
  local function bold(v) return { pandoc.Strong(to_inlines(v)) } end

  -- Capa
  if not is_empty(r.logo) then
    local w = is_empty(r['logo-width']) and '5cm' or stringify(r['logo-width'])
    add(styled('Capa', { pandoc.Image({}, stringify(r.logo), '', pandoc.Attr('', {}, { width = w })) }))
  end
  if not is_empty(r.institution) then add(styled('Capa', bold(r.institution))) end
  if not is_empty(r.department) then add(styled('Capa', to_inlines(r.department))) end
  if not is_empty(r.course) then add(styled('Capa', to_inlines(r.course))) end
  for i, a in ipairs(as_list(r.authors)) do
    add(styled(i == 1 and 'CapaEspaco' or 'Capa', to_inlines(a)))
  end
  add(styled('CapaTitulo', bold(r.title)))
  if not is_empty(r.subtitle) then add(styled('Capa', to_inlines(r.subtitle))) end
  add(styled('CapaRodape', to_inlines(r.city)))
  add(styled('Capa', to_inlines(r.year)))
  add(PAGEBREAK)

  -- Folha de rosto
  for _, a in ipairs(as_list(r.authors)) do add(styled('Capa', to_inlines(a))) end
  add(styled('CapaTitulo', bold(r.title)))
  if not is_empty(r.subtitle) then add(styled('Capa', to_inlines(r.subtitle))) end
  if not is_empty(r.nature) then add(styled('Natureza', to_inlines(r.nature))) end
  if not is_empty(r.advisor) then
    local label = is_empty(r['advisor-label']) and 'Orientador:' or stringify(r['advisor-label'])
    local inl = pandoc.Inlines { pandoc.Str(label), pandoc.Space() }
    inl:extend(to_inlines(r.advisor))
    add(styled('NaturezaOrientador', inl))
  end
  add(styled('CapaRodape', to_inlines(r.city)))
  add(styled('Capa', to_inlines(r.year)))
  add(PAGEBREAK)

  local function abstract_page(heading, body, kwlabel, kws)
    if is_empty(body) then return end
    add(styled('Capa', { pandoc.Strong { pandoc.Str(heading) } }))
    add(styled('Resumo', to_inlines(body)))
    if not is_empty(kws) then
      add(styled('Resumo', { pandoc.Strong { pandoc.Str(kwlabel) }, pandoc.Space(), pandoc.Str(keywords_text(kws)) }))
    end
    add(PAGEBREAK)
  end
  abstract_page('RESUMO', r.resumo, 'Palavras-chave:', r['palavras-chave'])
  abstract_page('ABSTRACT', r.abstract, 'Keywords:', r.keywords)
  return B
end

---------------------------------------------------------------------------
-- ABNT NBR 14724: the identification ("Figura N – ...", "Tabela N – ...")
-- goes ABOVE the figure or table, and the "Fonte: ..." line below it.
-- LaTeX: the "Fonte: ..." paragraph written right after a figure or table is
-- pulled into the same float, so caption, body and source never split across
-- pages. DOCX: the figure caption is moved above the image and both captions
-- get the "Figura N – " / "Tabela N – " prefix (pandoc's DOCX has no numbering).
-- Tables become `tabular` (not `longtable`, which breaks across pages).
-- Image paths are resolved against --resource-path here, since raw LaTeX
-- bypasses pandoc's lookup.
---------------------------------------------------------------------------
local function resolve(src)
  if src:match('^%a[%w+.-]*://') or src:sub(1, 1) == '/' then return src end
  for _, dir in ipairs(PANDOC_STATE.resource_path or {}) do
    local p = (dir == '.' or dir == '') and src or (dir .. '/' .. src)
    local f = io.open(p, 'r')
    if f then f:close(); return p end
  end
  return src
end

local function is_source(blk)
  return blk and blk.t == 'Para' and stringify(blk.content):match('^Fonte:') ~= nil
end

local function source_tex(blk)
  if not blk then return '' end
  return '\\par\\vspace{4pt}{\\raggedright\\small ' .. tex(blk.content) .. '\\par}'
end

-- A PNG with a same-named PDF beside it (e.g. a rendered diagram) uses the
-- vector PDF in the LaTeX output; the DOCX keeps the PNG.
local function prefer_pdf(path)
  local pdf = path:gsub('%.png$', '.pdf')
  if pdf == path then return path end
  local f = io.open(pdf, 'r')
  if f then f:close(); return pdf end
  return path
end

local function figure_tex(fig, src)
  local content = fig.content:walk {
    Image = function(img) img.src = prefer_pdf(resolve(img.src)); return img end,
  }
  local body = pandoc.write(pandoc.Pandoc(content), 'latex')
  local cap = tex(utils.blocks_to_inlines(fig.caption.long))
  local label = fig.identifier ~= '' and ('\\label{' .. fig.identifier .. '}') or ''
  return table.concat({
    '\\begin{figure}[!htbp]', '\\centering', '\\caption{' .. cap .. '}' .. label,
    body, source_tex(src), '\\end{figure}',
  }, '\n')
end

local function table_tex(tbl, src)
  local cap = tex(utils.blocks_to_inlines(tbl.caption.long))
  tbl.caption = pandoc.Caption()
  local lt = pandoc.write(pandoc.Pandoc({ tbl }), 'latex')
  local body = lt
    :gsub('{\\def\\LTcaptype{none}[^\n]*\n', '', 1)
    :gsub('}%s*$', '')
    :gsub('\\begin{longtable}%[%]', '\\begin{tabular}')
    :gsub('\\endhead\n', '')
    :gsub('\\bottomrule\\noalign{}\n\\endlastfoot\n', '')
    :gsub('\\end{longtable}', '\\bottomrule\\noalign{}\n\\end{tabular}')
  return table.concat({
    '\\begin{table}[!htbp]', '\\centering', '\\caption{' .. cap .. '}',
    body, source_tex(src), '\\end{table}',
  }, '\n')
end

local n_fig, n_tab = 0, 0

local function prefixed(label, n, inlines)
  local out = pandoc.Inlines { pandoc.Str(label .. ' ' .. n .. ' – ') }
  out:extend(inlines)
  return out
end

local function docx_blocks(blocks)
  local out = pandoc.Blocks {}
  for _, b in ipairs(blocks) do
    if b.t == 'Figure' then
      n_fig = n_fig + 1
      local cap = prefixed('Figura', n_fig, utils.blocks_to_inlines(b.caption.long))
      out:insert(pandoc.Div({ pandoc.Para(cap) }, { ['custom-style'] = 'Image Caption' }))
      local img = pandoc.Blocks(b.content)[1]
      out:insert(pandoc.Div({ pandoc.Para(img.content) }, { ['custom-style'] = 'Captioned Figure' }))
    elseif b.t == 'Table' then
      n_tab = n_tab + 1
      b.caption.long = { pandoc.Plain(prefixed('Tabela', n_tab, utils.blocks_to_inlines(b.caption.long))) }
      out:insert(b)
    else
      out:insert(b)
    end
  end
  return out
end

function Blocks(blocks)
  if FORMAT:match('docx') then return docx_blocks(blocks) end
  if not FORMAT:match('latex') then return nil end
  local out, i = pandoc.Blocks {}, 1
  while i <= #blocks do
    local b, nxt = blocks[i], blocks[i + 1]
    if b.t == 'Figure' or b.t == 'Table' then
      local src = is_source(nxt) and nxt or nil
      local f = b.t == 'Figure' and figure_tex or table_tex
      out:insert(pandoc.RawBlock('latex', f(b, src)))
      i = i + (src and 2 or 1)
    else
      out:insert(b)
      i = i + 1
    end
  end
  return out
end

---------------------------------------------------------------------------
-- ```{.python include="../path/file.py"}``` -> the file's text (path relative
-- to the report folder). Used for code appendices; works for PDF and DOCX.
---------------------------------------------------------------------------
function CodeBlock(cb)
  local path = cb.attributes.include
  if not path then return nil end
  local f = io.open(path, 'r')
  if not f then
    io.stderr:write('ufjf-front.lua: cannot read ' .. path .. '\n')
    return nil
  end
  cb.text = (f:read('a'):gsub('\n+$', ''))
  f:close()
  cb.attributes.include = nil
  return cb
end

---------------------------------------------------------------------------
function Pandoc(doc)
  local r = doc.meta.report
  if r == nil then
    io.stderr:write('ufjf-front.lua: no `report:` metadata (report.yaml); skipping front matter\n')
    return doc
  end

  -- Document properties (PDF info / DOCX core props).
  doc.meta['title-meta'] = stringify(r.title)
  doc.meta['author-meta'] = joined(r.authors, '; ')
  if FORMAT:match('docx') then
    -- (Not for LaTeX: pandoc 3.9's template emits \xmpquote for keywords,
    -- which is undefined unless hyperxmp is loaded.)
    local kw = pandoc.List {}
    for _, k in ipairs(as_list(r['palavras-chave'])) do kw:insert(stringify(k)) end
    doc.meta.keywords = kw
  end

  if FORMAT:match('latex') then
    local inc = doc.meta['include-before'] or pandoc.List {}
    if utils.type(inc) ~= 'List' then inc = pandoc.List { inc } end
    inc:insert(1, pandoc.MetaBlocks { latex_front(r) })
    doc.meta['include-before'] = inc
    -- Textual pages start on a fresh, numbered page (after SUMÁRIO/lists).
    doc.blocks:insert(1, pandoc.RawBlock('latex', '\\clearpage\\pagestyle{fancy}'))
  elseif FORMAT:match('docx') then
    local front = docx_front(r)
    front:extend(doc.blocks)
    doc.blocks = front
  end
  return doc
end
