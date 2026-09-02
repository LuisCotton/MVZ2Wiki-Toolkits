local p = {}
local cache

local rechargeNames = {
    none = '',
    short = '短',
    long = '长',
    very_long = '很长',
}

local function loadData()
    if cache then
        return cache
    end
    local title = mw.title.new('Almanac.json')
    if not title or not title.exists then
        return nil
    end
    local ok, decoded = pcall(mw.text.jsonDecode, title:getContent() or '')
    if not ok or type(decoded) ~= 'table' then
        return nil
    end
    cache = {}
    for _, item in ipairs(decoded) do
        if item.id then
            cache[item.id] = item
            cache[item.id:lower()] = item
        end
        if item.name then
            cache[item.name] = item
            cache[item.name:lower()] = item
        end
    end
    return cache
end

local function stripPrefix(value)
    if type(value) ~= 'string' then
        return value
    end
    return (value:gsub('^mvz2:', ''))
end

local function nonEmpty(value)
    return value ~= nil and value ~= ''
end

local function format(text)
    if type(text) ~= 'string' then
        return ''
    end
    return text:gsub('<color=([^>]+)>', '<span style="color:%1">'):gsub('</color>', '</span>')
        :gsub('{{Tag|([^|{}]+)|([^|{}]+)|text=no}}', '{{标签图标|%1|%2}}')
        :gsub('{{标签图标|([^|{}]+)|([^|{}]+)|no}}', '{{标签图标|%1|%2}}')
end

local function plain(text)
    text = format(text)
    return mw.text.trim((text:gsub('<[^>]+>', '')))
end

local function join(value, separator)
    if type(value) == 'table' then
        local result = {}
        for _, text in ipairs(value) do
            if text ~= '' then table.insert(result, format(text)) end
        end
        return table.concat(result, separator or '')
    end
    if value and value ~= '' then return format(value) end
    return ''
end

local function override(frame, name, aliases)
    if nonEmpty(frame.args[name]) then
        return frame.args[name]
    end
    for _, alias in ipairs(aliases or {}) do
        if nonEmpty(frame.args[alias]) then
            return frame.args[alias]
        end
    end
    return nil
end

local function icon(item, page)
    local id = stripPrefix(item.id or '')
    if id and id ~= '' then
        return 'mvz2_entity.' .. id:gsub('_', ' ') .. '.png'
    end
    return ''
end

local function tagText(tag)
    if type(tag) ~= 'table' then
        return ''
    end
    return string.format('{{标签图标|%s|%s}}', tag[1] or tag.kind or tag.id or '', tag[2] or tag.value or tag.name or '')
end

local function hasMassTag(tags)
    for _, tag in ipairs(tags or {}) do
        local kind = tag[1] or tag.kind or tag.id or ''
        if kind == '质量' or kind == 'mass' then
            return true
        end
    end
    return false
end

local function field(item, key)
    local fields = item.almanacFields or {}
    if nonEmpty(fields[key]) then
        return fields[key]
    end
    local info = item.infobox or {}
    if nonEmpty(info[key]) then
        return info[key]
    end
    return nil
end

local function recharge(item)
    local info = item.infobox or {}
    local value = stripPrefix(info.rechargeId or item.recharge or '')
    return rechargeNames[value] or value
end

local function formatNumber(value)
    local number = tonumber(value)
    if not number then
        return value
    end
    if number == math.floor(number) then
        return tostring(math.floor(number))
    end
    return tostring(number)
end

local function params(frame, item, page)
    local result = {
        ' | language = ' .. (override(frame, 'language', { '语言' }) or 'zh_CN'),
        ' | name = ' .. (override(frame, 'name', { '名称' }) or item.name or page or ''),
        ' | icon = ' .. (override(frame, 'icon', { '图标名' }) or icon(item, page)),
        ' | desc = ' .. (override(frame, 'desc', { '主描述' }) or join(item.header, '<br>')),
    }

    for index = 1, 15 do
        local explicit = override(frame, 'tag' .. index, { '标签' .. index })
        if explicit ~= nil then
            table.insert(result, ' | tag' .. index .. '=' .. explicit)
        elseif item.tags and item.tags[index] then
            table.insert(result, ' | tag' .. index .. '=' .. tagText(item.tags[index]))
        elseif item.type == 'enemy' and index == #(item.tags or {}) + 1 and not hasMassTag(item.tags) then
            table.insert(result, ' | tag' .. index .. '={{标签图标|质量|中}}')
        end
    end

    local outputFields = {
        { 'toughness', { '耐久' }, field(item, 'toughness') },
        { 'firerate', { '攻速', '发射速度' }, field(item, 'firerate') },
        { 'damage', { '伤害' }, field(item, 'damage') },
        { 'producetime', { '生产速度', '生产时间' }, field(item, 'producetime') },
        { 'production', { '提供能量' }, field(item, 'production') },
        { 'special', { '特点' }, field(item, 'special') },
        { 'evocation', { '技能' }, field(item, 'evocation') },
    }
    for _, spec in ipairs(outputFields) do
        local name, aliases, value = spec[1], spec[2], spec[3]
        table.insert(result, ' | ' .. name .. ' = ' .. (override(frame, name, aliases) or formatNumber(value or '') or ''))
    end

    table.insert(result, ' | flavor = ' .. (override(frame, 'flavor', { '描述' }) or plain(join(item.flavor, '<br>'))))
    if item.type ~= 'enemy' then
        table.insert(result, ' | cost = ' .. (override(frame, 'cost', { '花费' }) or formatNumber(item.cost or field(item, 'cost') or '') or ''))
    end
    table.insert(result, ' | recharge = ' .. (override(frame, 'recharge', { '冷却时间', '充能时间' }) or recharge(item) or ''))

    return table.concat(result, '\n')
end

function p.getAlmanac(frame)
    local data = loadData()
    if not data then
        return '错误：无法加载 [[Almanac.json]]'
    end
    local key = frame.args[1]
    if not key or key == '' then
        local parent = frame:getParent()
        if parent then
            key = parent:getTitle():gsub('^[^:]+:', '')
        end
    end
    if not key or key == '' then
        return '错误：请提供图鉴条目名或ID。'
    end
    local item = data[key] or data[key:lower()]
    if not item then
        return '错误：在 [[Almanac.json]] 中未找到「' .. key .. '」的数据'
    end
    return frame:preprocess('{{Almanac\n' .. params(frame, item, key) .. '\n}}')
end

return p