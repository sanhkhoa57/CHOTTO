package vn.chotto.app

/**
 * Lý do hiển thị theo ngôn ngữ. Engine luôn viết lý do bằng tiếng Việt; bản tiếng Anh dựng lại từ mã dấu hiệu
 * và các chi tiết lấy từ câu tiếng Việt (cùng cách với `viewmodel._REASONS_EN` bên Desktop).
 * Thêm mã dấu hiệu mới thì phải thêm bản dịch ở đây.
 */
object Reasons {
    private fun find(pattern: String, text: String): List<String>? =
        Regex(pattern).find(text)?.groupValues?.drop(1)

    fun text(s: LinkInspector.Signal, lang: String): String {
        if (lang != "en") return s.reason
        val b = s.brand
        val r = s.reason
        return when (s.code) {
            "blacklist" -> "This domain is on a scam list reported by the community"
            "unparseable" -> "CHOTTO could not analyse this link; check it carefully before opening"
            "combosquat" -> "The domain contains the name “$b” but is not the official site"
            "homoglyph" -> "Uses look-alike characters (0/o, 1/l, rn/m, Cyrillic…) to imitate $b"
            "typosquat" -> find("sai lệch (\\d+)", r)?.let { "Imitates the brand $b (${it[0]} character(s) off)" }
                ?: "Imitates the brand $b"
            "lure" -> find("“(.+?)”", r)?.let { "Contains an alarming keyword: “${it[0]}”" } ?: "Contains an alarming keyword"
            "brand_in_path" -> find("địa chỉ (\\S+) để", r)?.let { "The path inserts ${it[0]} to pose as $b" } ?: r
            "tld" -> find("Đuôi \\.(\\S+)", r)?.let { "The .${it[0].removeSuffix("thường")} ending is often abused for scams" } ?: r
            "idn" -> "The domain uses Unicode characters that are easy to fake"
            "entropy" -> "The domain looks like a random string of characters"
            "hyphens" -> "The domain has an unusual number of hyphens"
            "digits" -> "The domain contains many random digits"
            "free_hosting" -> "The page is on a free website builder anyone can use in minutes"
            "nested_redirect" -> "The link is wrapped in many redirects to hide where it goes"
            "http" -> "The link is not encrypted (http://)"
            "at_sign" -> "Contains an @ sign to hide the real domain"
            "port" -> find("\\(:(\\d+)\\)", r)?.let { "Uses an unusual network port (:${it[0]})" } ?: "Uses an unusual network port"
            "shortener" -> "A short link hides the real destination"
            "raw_ip" -> "Uses an IP address instead of a domain name"
            "redirect_via_trusted" -> find("Đi qua (\\S+) để chuyển hướng sang (\\S+)", r)
                ?.let { "Goes through ${it[0]} to redirect to ${it[1]}" } ?: r
            "age" -> find("(\\d+) ngày", r)?.let { "Domain registered only ${it[0]} day(s) ago" } ?: "Domain registered very recently"
            else -> r
        }
    }
}
