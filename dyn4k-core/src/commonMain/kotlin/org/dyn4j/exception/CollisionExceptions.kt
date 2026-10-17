/*
 * Copyright (c) 2010-2024 William Bittle  http://www.dyn4j.org/
 * All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without modification, are permitted
 * provided that the following conditions are met:
 *
 *   * Redistributions of source code must retain the above copyright notice, this list of conditions
 *     and the following disclaimer.
 *   * Redistributions in binary form must reproduce the above copyright notice, this list of conditions
 *     and the following disclaimer in the documentation and/or other materials provided with the
 *     distribution.
 *   * Neither the name of the copyright holder nor the names of its contributors may be used to endorse or
 *     promote products derived from this software without specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR
 * IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND
 * FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
 * CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
 * DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
 * DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER
 * IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT
 * OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 */
package org.dyn4j.exception

internal fun copyExceptionMessage(sourceName: String, copyName: String) =
    "The copy method on class '$sourceName' returns an object of class '$copyName'. " +
        "You must override the copy method to return type '$sourceName'."

expect open class CopyException(sourceName: String, copyName: String) : ClassCastException

open class ObjectAlreadyExistsException(argumentName: String, objectValue: Any?, owner: Any?) :
    IllegalArgumentException("$argumentName is set to an object: $objectValue that already exists in: $owner")

open class ObjectAlreadyOwnedException(argumentName: String, objectValue: Any?, owner: Any?) :
    IllegalArgumentException("The object given for $argumentName: $objectValue is already owned by another object: $objectValue")

open class SameObjectException(argumentName1: String, argumentName2: String, objectValue: Any?) :
    IllegalArgumentException("$argumentName1 and $argumentName2 cannot be the same object. Both were: $objectValue")
