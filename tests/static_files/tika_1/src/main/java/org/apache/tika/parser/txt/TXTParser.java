/**
 * Licensed to the Apache Software Foundation (ASF) under one or more
 * contributor license agreements.  See the NOTICE file distributed with
 * this work for additional information regarding copyright ownership.
 * The ASF licenses this file to You under the Apache License, Version 2.0
 * (the "License"); you may not use this file except in compliance with
 * the License.  You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
package org.apache.tika.parser.txt;

import java.io.IOException;
import java.io.InputStream;
import java.io.Reader;

import org.apache.tika.exception.TikaException;
import org.apache.tika.metadata.Metadata;
import org.apache.tika.parser.Parser;
import org.apache.tika.sax.XHTMLContentHandler;
import org.apache.tika.utils.Utils;
import org.xml.sax.ContentHandler;
import org.xml.sax.SAXException;

/**
 * Text parser
 */
public class TXTParser implements Parser {

    public void parse(
            InputStream stream, ContentHandler handler, Metadata metadata)
            throws IOException, SAXException, TikaException {
        
        Reader reader = Utils.getUTF8Reader(stream, metadata);
        metadata.set(Metadata.CONTENT_TYPE, "text/plain");

        XHTMLContentHandler xhtml = new XHTMLContentHandler(handler, metadata);
        xhtml.startDocument();
        xhtml.startElement("p");
        char[] buffer = new char[4096];
        for (int n = reader.read(buffer); n != -1; n = reader.read(buffer)) {
            xhtml.characters(buffer, 0, n);
        }
        xhtml.endElement("p");
        xhtml.endDocument();
    }

}
