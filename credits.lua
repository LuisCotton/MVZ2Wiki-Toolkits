local p = {}

local dataCache

local function loadData()
    if dataCache then
        return dataCache
    end
    local ok, data = pcall(mw.loadJsonData, 'Credits.json')
    if not ok or type(data) ~= 'table' then
        local title = mw.title.new('Credits.json')
        if not title or not title.exists then
            return nil
        end
        ok, data = pcall(mw.text.jsonDecode, title:getContent() or '')
        if not ok or type(data) ~= 'table' then
            return nil
        end
    end
    dataCache = data.categories or data
    return dataCache
end

local function categoryText(category)
    if type(category) ~= 'table' then
        return nil
    end

    local name = category.name or ''
    local entries = category.entries or {}
    local result = {';' .. name}

    if type(entries) == 'table' then
        for _, entry in ipairs(entries) do
            if entry ~= nil and entry ~= '' then
                table.insert(result, ':' .. tostring(entry))
            end
        end
    end

    return table.concat(result, '\n')
end

function p.getCredits(frame)
    local data = loadData()
    if not data then
        return '错误：无法加载 [[Credits.json]]'
    end

    local result = {}
    for _, category in ipairs(data) do
        local text = categoryText(category)
        if text then
            table.insert(result, text)
        end
    end
    return table.concat(result, '\n')
end

function p.main(frame)
    return p.getCredits(frame)
end

return p