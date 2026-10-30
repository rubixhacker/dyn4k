package io.github.rubixhacker.harness.qualification

import io.github.rubixhacker.harness.contract.PublicationContract
import java.nio.file.Path
import javax.xml.parsers.DocumentBuilderFactory
import javax.xml.parsers.ParserConfigurationException
import org.w3c.dom.Element
import org.w3c.dom.Node
import org.xml.sax.SAXException

/** Thrown when a staged POM is not well-formed XML. */
class PomParseException(message: String) : Exception(message)

/**
 * POM element rules of `qualify.pom_element_matches` and `qualify.pom_metadata_contract`.
 *
 * The reference walks an `ElementTree` subtree, so the port reproduces ElementTree's view of a
 * node: the tag with its namespace in braces, child *elements* only, the leading text node, and
 * the tail text after each child.
 */
object PomContract {
    const val NAMESPACE = "http://maven.apache.org/POM/4.0.0"

    fun qualified(name: String): String = "{$NAMESPACE}$name"

    fun tag(element: Element): String =
        if (element.namespaceURI == null) element.tagName else "{${element.namespaceURI}}${element.localName}"

    fun childElements(element: Element): List<Element> {
        val children = mutableListOf<Element>()
        var node = element.firstChild
        while (node != null) {
            if (node.nodeType == Node.ELEMENT_NODE) children.add(node as Element)
            node = node.nextSibling
        }
        return children
    }

    /** `element.text` in ElementTree: the leading text node, or null when there is none. */
    fun text(element: Element): String? {
        val first = element.firstChild ?: return null
        return if (first.nodeType == Node.TEXT_NODE || first.nodeType == Node.CDATA_SECTION_NODE) {
            first.nodeValue
        } else {
            null
        }
    }

    /** `element.tail` in ElementTree: the text node that follows the element. */
    fun tail(element: Element): String? {
        val next = element.nextSibling ?: return null
        return if (next.nodeType == Node.TEXT_NODE || next.nodeType == Node.CDATA_SECTION_NODE) {
            next.nodeValue
        } else {
            null
        }
    }

    fun attributes(element: Element): Map<String, String> {
        val map = element.attributes
        val result = LinkedHashMap<String, String>()
        for (index in 0 until map.length) {
            val item = map.item(index)
            result[item.nodeName] = item.nodeValue
        }
        return result
    }

    fun find(parent: Element, name: String): Element? =
        childElements(parent).firstOrNull { tag(it) == qualified(name) }

    /** `Element.findtext`: the leading text of the first matching child, or null when absent. */
    fun findText(parent: Element, name: String): String? = find(parent, name)?.let { text(it) ?: "" }

    /** `Element.findall(ns + container + "/" + ns + name)`. */
    fun findAll(parent: Element, containerName: String, name: String): List<Element> {
        val container = find(parent, containerName) ?: return emptyList()
        return childElements(container).filter { tag(it) == qualified(name) }
    }

    /**
     * `qualify.pom_element_matches`: an element is a match when its tag, attributes, text, and
     * children match the expected string or ordered nested contract exactly.
     */
    fun elementMatches(element: Element?, name: String, expected: Any?): Boolean {
        if (element == null || tag(element) != qualified(name) || attributes(element).isNotEmpty()) return false
        if (expected is String) {
            return childElements(element).isEmpty() && text(element) == expected
        }
        if (expected !is Map<*, *>) return false
        if (!(text(element) ?: "").trim().isEmpty()) return false
        val children = childElements(element)
        if (children.size != expected.size) return false
        var index = 0
        for ((key, value) in expected) {
            val child = children[index]
            index += 1
            if (!elementMatches(child, key as String, value)) return false
            if (!(tail(child) ?: "").trim().isEmpty()) return false
        }
        return true
    }

    /** `qualify.pom_metadata_contract`, in the order the audit compares the sections. */
    fun metadata(module: String): Map<String, Any> {
        val metadata = PublicationContract.pomMetadata(module)
        return linkedMapOf(
            "name" to metadata.name,
            "description" to metadata.description,
            "url" to metadata.url,
            "licenses" to linkedMapOf(
                "license" to linkedMapOf("name" to metadata.licenseName, "url" to metadata.licenseUrl),
            ),
            "developers" to linkedMapOf(
                "developer" to linkedMapOf("id" to metadata.developerId, "name" to metadata.developerName),
            ),
            "scm" to linkedMapOf("url" to metadata.scmUrl),
        )
    }

    /** Parses a staged POM, mapping XML failures onto [PomParseException]. */
    fun parse(path: Path): Element {
        val factory = DocumentBuilderFactory.newInstance()
        factory.isNamespaceAware = true
        runCatching {
            factory.setFeature("http://xml.org/sax/features/external-general-entities", false)
            factory.setFeature("http://xml.org/sax/features/external-parameter-entities", false)
            factory.setAttribute(javax.xml.XMLConstants.ACCESS_EXTERNAL_DTD, "")
            factory.setAttribute(javax.xml.XMLConstants.ACCESS_EXTERNAL_SCHEMA, "")
        }
        return try {
            val builder = factory.newDocumentBuilder()
            builder.setErrorHandler(null)
            builder.parse(path.toFile()).documentElement
        } catch (error: SAXException) {
            throw PomParseException(error.message ?: "invalid XML")
        } catch (error: ParserConfigurationException) {
            throw PomParseException(error.message ?: "invalid XML")
        } catch (error: java.io.IOException) {
            throw BadArchiveException(error.message ?: "unreadable POM", error)
        }
    }
}
