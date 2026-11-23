package vn.chotto.app

/**
 * "AI's Advices" cục bộ, port từ `chotto/advisor.py` (vi + en): ưu tiên tổ hợp dấu hiệu, rồi từng dấu hiệu.
 * Không gửi dữ liệu ra ngoài.
 */
object Advisor {
    private val IMPERSONATION = setOf("combosquat", "homoglyph", "typosquat")
    private val REDIRECTS = setOf("redirect_via_trusted", "nested_redirect")

    /** Nhóm dấu hiệu của từng tổ hợp (cùng thứ tự với [COMBOS_VI] và [COMBOS_EN]). */
    private val COMBO_GROUPS: List<List<Set<String>>> = listOf(
        listOf(IMPERSONATION, setOf("age")),
        listOf(IMPERSONATION, setOf("lure")),
        listOf(IMPERSONATION, setOf("free_hosting")),
        listOf(IMPERSONATION, REDIRECTS),
        listOf(setOf("shortener"), setOf("lure")),
        listOf(setOf("raw_ip", "port"), setOf("lure", "http")),
    )

    private val TIPS_VI = mapOf(
        "blacklist" to "Trang này đã bị cộng đồng báo cáo là lừa đảo. Đừng nhập bất kỳ thông tin nào và hãy báo cho người gửi biết.",
        "combosquat" to "Đừng đăng nhập qua link trong tin nhắn. Hãy tự mở ứng dụng hoặc gõ địa chỉ chính thức của {brand}.",
        "homoglyph" to "Địa chỉ này giả dạng {brand} bằng ký tự nhìn giống nhau. Hãy kiểm tra từng chữ cái trong tên miền.",
        "typosquat" to "Tên miền gần giống {brand} nhưng sai vài ký tự, đây là chiêu giả mạo phổ biến.",
        "lure" to "Các từ như “khóa tài khoản”, “phạt nguội”, “hoàn thuế” thường dùng để tạo cảm giác khẩn cấp. Hãy bình tĩnh và xác minh qua kênh chính thức.",
        "tld" to "Đuôi tên miền giá rẻ thường được kẻ lừa đảo đăng ký hàng loạt.",
        "raw_ip" to "Dịch vụ thật hiếm khi dùng địa chỉ IP trần. Không nhập thông tin cá nhân vào trang này.",
        "at_sign" to "Phần đứng trước ký tự @ không phải trang đích thật. Đừng mở link này.",
        "shortener" to "Link rút gọn che đích đến thật. Hãy hỏi người gửi địa chỉ đầy đủ.",
        "nested_redirect" to "Liên kết được bọc nhiều lớp chuyển hướng để giấu trang đích. Đừng mở nếu không chắc chắn.",
        "redirect_via_trusted" to "Liên kết mượn một trang uy tín để chuyển hướng bạn sang trang khác. Hãy xem kỹ trang đích.",
        "brand_in_path" to "Tên ngân hàng/dịch vụ xuất hiện ở phần sau của địa chỉ chỉ để đánh lừa; trang thật nằm ở phần tên miền đứng trước.",
        "http" to "Trang không mã hóa, thông tin nhập vào có thể bị đọc trộm.",
        "port" to "Trang dùng cổng mạng lạ, dấu hiệu của máy chủ dựng tạm.",
        "idn" to "Tên miền chứa ký tự Unicode có thể trông giống hệt chữ Latin. Hãy gõ tay địa chỉ chính thức.",
        "entropy" to "Tên miền kiểu chuỗi ngẫu nhiên thường do công cụ tự sinh cho chiến dịch lừa đảo.",
        "hyphens" to "Nhiều dấu gạch ngang là đặc điểm của tên miền ghép để giả mạo.",
        "digits" to "Tên miền chứa nhiều chữ số ngẫu nhiên, thường thấy ở trang lừa đảo dựng hàng loạt.",
        "free_hosting" to "Trang được dựng trên nền tảng miễn phí, ngân hàng và cơ quan nhà nước không dùng loại địa chỉ này.",
        "age" to "Tên miền vừa được đăng ký gần đây; trang lừa đảo thường chỉ sống vài ngày.",
        "unparseable" to "Liên kết có định dạng bất thường. Hãy hỏi lại người gửi trước khi mở.",
    )
    private val COMBOS_VI = listOf(
        "Trang giả {brand} trên một tên miền vừa đăng ký vài ngày: gần như chắc chắn là lừa đảo. Tuyệt đối không đăng nhập hay nhập mã OTP.",
        "Đây là kịch bản quen thuộc: giả danh {brand} rồi hối thúc bạn xử lý gấp. {brand} không yêu cầu xác nhận hay mở khóa qua link; hãy gọi tổng đài in trên thẻ hoặc mở ứng dụng chính thức.",
        "{brand} không bao giờ đặt trang đăng nhập trên nền tảng tạo web miễn phí. Đây là trang giả.",
        "Liên kết đi vòng qua một trang uy tín rồi mới tới trang giả {brand}, để qua mặt bạn và bộ lọc.",
        "Link rút gọn đi kèm lời hối thúc: kẻ gian che địa chỉ thật để bạn không kịp nhận ra. Hãy hỏi người gửi địa chỉ đầy đủ qua một kênh khác.",
        "Trang đặt trên máy chủ dựng tạm (địa chỉ IP hoặc cổng lạ), không mã hóa. Không nhập bất kỳ thông tin nào.",
    )
    private const val GENERAL_VI =
        "Ngân hàng, cơ quan nhà nước không yêu cầu cung cấp OTP, mật khẩu hay CCCD qua đường link trên Zalo. " +
            "Nếu nghi ngờ, hãy gọi hotline chính thức hoặc hỏi người thân trước khi bấm."

    private val TIPS_EN = mapOf(
        "blacklist" to "This page has been reported as a scam. Don't enter any information, and let the sender know.",
        "combosquat" to "Don't sign in through a link in a message. Open the app yourself or type the official {brand} address.",
        "homoglyph" to "This address imitates {brand} with look-alike characters. Check every letter of the domain.",
        "typosquat" to "The domain is almost {brand} but a few characters off, a common impersonation trick.",
        "lure" to "Words like “account locked”, “traffic fine” or “tax refund” are used to create panic. Stay calm and verify through an official channel.",
        "tld" to "Cheap domain endings are often registered in bulk by scammers.",
        "raw_ip" to "Real services rarely use a bare IP address. Don't enter personal details on this page.",
        "at_sign" to "Everything before the @ sign is not the real destination. Don't open this link.",
        "shortener" to "A short link hides where it really goes. Ask the sender for the full address.",
        "nested_redirect" to "The link is wrapped in several redirects to hide the destination. Don't open it unless you're sure.",
        "redirect_via_trusted" to "The link borrows a trusted site to send you somewhere else. Look closely at the destination.",
        "brand_in_path" to "The bank or service name appears later in the address only to mislead you; the real site is the domain before it.",
        "http" to "The page isn't encrypted, so anything you type can be read by others.",
        "port" to "The page uses an unusual network port, a sign of a makeshift server.",
        "idn" to "The domain contains Unicode characters that can look exactly like Latin letters. Type the official address yourself.",
        "entropy" to "Random-looking domains are usually generated by tools for scam campaigns.",
        "hyphens" to "Many hyphens are typical of domains stitched together to impersonate a brand.",
        "digits" to "The domain has many random digits, common on scam pages built in bulk.",
        "free_hosting" to "The page is built on a free platform; banks and government agencies never use addresses like this.",
        "age" to "The domain was registered very recently; scam pages usually live only a few days.",
        "unparseable" to "The link has an unusual format. Ask the sender before opening it.",
    )
    private val COMBOS_EN = listOf(
        "A fake {brand} page on a domain registered a few days ago: almost certainly a scam. Never sign in or enter an OTP code.",
        "A familiar script: pretend to be {brand}, then rush you. {brand} never asks you to confirm or unlock anything through a link; call the number on your card or open the official app.",
        "{brand} never puts its sign-in page on a free website builder. This page is fake.",
        "The link detours through a trusted site before reaching a fake {brand} page, to fool you and the filters.",
        "A short link plus pressure to act fast: the scammer hides the real address so you don't notice. Ask the sender for the full address through another channel.",
        "The page runs on a makeshift server (bare IP or odd port) without encryption. Don't enter any information.",
    )
    private const val GENERAL_EN =
        "Banks and government agencies never ask for OTP codes, passwords or ID numbers through a link on Zalo. " +
            "If in doubt, call the official hotline or ask someone you trust before tapping."

    fun advise(signals: List<LinkInspector.Signal>, lang: String): String {
        val en = lang == "en"
        // Không phân tích được link: chỉ lời khuyên chung (giống engine.analysis_failed_result).
        if (signals.any { it.code == "unparseable" }) return if (en) GENERAL_EN else GENERAL_VI
        val tips = if (en) TIPS_EN else TIPS_VI
        val combos = if (en) COMBOS_EN else COMBOS_VI
        val defaultBrand = if (en) "this brand" else "thương hiệu này"
        val ordered = signals.filter { it.points > 0 }.sortedByDescending { it.points }
        val present = ordered.map { it.code }.toSet()
        val covered = mutableSetOf<String>()
        val parts = mutableListOf<String>()
        fun brandOf(codes: Set<String>) = ordered.firstOrNull { it.code in codes && it.brand.isNotEmpty() }?.brand ?: defaultBrand
        for ((i, groups) in COMBO_GROUPS.withIndex()) {
            if (parts.size == 2) break
            if (groups.all { (it intersect present).isNotEmpty() } &&
                !groups.all { covered.containsAll(it intersect present) }
            ) {
                val matched = groups.flatMap { it intersect present }.toSet()
                parts += combos[i].replace("{brand}", brandOf(matched))
                covered += matched
            }
        }
        for (s in ordered) {
            if (parts.size == 2) break
            val tip = tips[s.code] ?: continue
            if (!covered.add(s.code)) continue
            parts += tip.replace("{brand}", s.brand.ifEmpty { defaultBrand })
        }
        parts += if (en) GENERAL_EN else GENERAL_VI
        return parts.joinToString(" ")
    }
}
